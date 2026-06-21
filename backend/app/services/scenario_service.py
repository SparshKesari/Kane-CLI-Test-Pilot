from __future__ import annotations

import json
from typing import Optional

from ..config import get_settings
from ..models import ExistingTest

SYSTEM = """You are a senior QA test strategist. Given a web app's repo profile, its
EXISTING automated tests, and a RENDERED snapshot of its live UI (real DOM: links,
buttons, inputs, headings, visible text), propose the most valuable NEW end-to-end UI
test scenarios.

Hard rules:
- Each scenario is ONE tight user flow: EXACT start path, a crisp action sequence on
  elements that ACTUALLY appear in the snapshot, and a single observable result.
  End every objective with "Do not browse elsewhere."
- CONCRETE ASSERTIONS ONLY. Never write "the expected name", "the correct page", or other
  vague checks. Use exact strings from the snapshot — e.g. assert the title CONTAINS
  "Agent Skills for All", or that a card labeled "Selenium Skill" is visible. If you cannot
  state a concrete, observable expected value, do not propose that scenario.
- Prefer DEEP interaction flows (click a card/button → verify the resulting state/page)
  over shallow "page loads" checks. Avoid external-link / new-tab navigation scenarios
  (hard to verify reliably).
- A NEGATIVE scenario drives an invalid/error path (wrong credentials, missing required
  field, a query with no results) and asserts the error/empty state. An EDGE scenario
  covers a boundary/unusual state (an empty collection, a duplicate entry, special
  characters, a boundary value). A HAPPY scenario is the normal success path.
  Derive all of these from THIS app's actual UI — do not assume any particular domain.
- Only propose flows reachable from the snapshot — never invent features.
- If SOURCE CODE of the app's pages is provided, treat it as GROUND TRUTH. Use it to
  (a) target real routes/pages that the homepage snapshot doesn't reveal (e.g. detail
  pages, dynamic [id] routes), (b) take exact expected strings from the JSX/templates
  for concrete assertions, and (c) surface NEGATIVE/EDGE scenarios the code branches
  reveal — empty-result states, validation errors, loading/error fallbacks — asserting
  the exact fallback text the code renders. Prefer code-confirmed flows over guesses.
- Rank by user impact (auth, data, core interactions > cosmetic).
- Return STRICT JSON only: an array of objects with keys:
  title, objective, expected, feature, scenario_type (HAPPY|NEGATIVE|EDGE),
  criticality (HIGH|MEDIUM|LOW), rationale. No prose, no markdown fences."""

_AUTH_DATA_RULE = """
- AUTH & TEST DATA: the runner supplies throwaway test data you can reference in
  objectives with the {{var}} syntax — {{email}}, {{password}}, {{name}}, {{url}}.
  When a flow needs input, USE these (e.g. "type {{url}} into the URL field",
  "enter email {{email}} and password {{password}}"). For ANY flow that requires
  being signed in (settings, account, admin, profile, protected pages, or
  creating/saving data tied to a user), make the objective SELF-CONTAINED: begin by
  signing up OR logging in with {{email}}/{{password}}, THEN do and verify the
  action. Never propose a logged-in action without first establishing the session."""

_GREENFIELD_GOAL = """MODE: GREENFIELD — this project has little or no automated UI
coverage. GOAL: broad, comprehensive coverage. For EVERY major feature you can reach,
propose at least one HAPPY-path scenario. For HIGH-criticality features (authentication,
anything that mutates or deletes data, or handles money/permissions) ALSO propose NEGATIVE
and EDGE scenarios. Maximize distinct features covered rather than many variants of one.
Use the full budget."""

_GAPFILL_GOAL = """MODE: GAP-FILL — this project ALREADY has automated tests. Features
with existing coverage: {covered}. GOAL: fill the gaps only. Assume HAPPY paths for the
covered features already exist — for those, propose NEGATIVE and EDGE scenarios on the
HIGH-criticality ones. For features with NO existing coverage, propose full coverage
(HAPPY first, then NEGATIVE). NEVER re-propose a flow an existing test already covers."""


def propose(
    profile: dict,
    existing: list[ExistingTest],
    crawl: dict,
    target_url: str,
    *,
    mode: str = "greenfield",
    budget: int = 20,
    covered_features: list[str] | None = None,
    code_map: dict | None = None,
) -> list[dict]:
    """Return up to `budget` ranked, deduped scenario dicts with stable ids.
    `mode` is "greenfield" (broad coverage) or "gapfill" (only missing cases).
    `code_map` (from code_intel) grounds scenarios in the app's real source.
    Uses the LLM when ANTHROPIC_API_KEY is set; otherwise a heuristic fallback."""
    s = get_settings()
    covered_features = covered_features or []
    raw = (_llm(profile, existing, crawl, target_url, budget, mode, covered_features, code_map)
           if s.anthropic_api_key else
           _heuristic(profile, existing, crawl, target_url, budget, mode, covered_features))
    return _assign_ids(raw[:budget])


def _assign_ids(items: list[dict]) -> list[dict]:
    out = []
    for i, it in enumerate(items, 1):
        sid = f"SC-{i:03d}"
        out.append({
            "id": sid,
            "requirement_id": f"AC-{i:03d}",
            "title": it.get("title", sid),
            "objective": it.get("objective", ""),
            "expected": it.get("expected", ""),
            "feature": it.get("feature", "GENERAL"),
            "scenario_type": str(it.get("scenario_type", "HAPPY")).upper(),
            "criticality": it.get("criticality", "MEDIUM"),
            "rationale": it.get("rationale", ""),
        })
    return out


# --------------------------------------------------------------------------- #
def _llm(profile, existing, crawl, target_url, budget, mode, covered, code_map=None) -> list[dict]:
    s = get_settings()
    from anthropic import Anthropic

    client = Anthropic(api_key=s.anthropic_api_key)
    existing_brief = [f"{t.name} ({t.file}): {t.target}" for t in existing][:60]
    goal = (_GAPFILL_GOAL.format(covered=", ".join(covered) or "(none detected)")
            if mode == "gapfill" else _GREENFIELD_GOAL)
    payload = {
        "target_url": target_url,
        "repo_profile": profile,
        "existing_tests": existing_brief,
        "live_ui": crawl,
        "how_many": budget,
    }
    if code_map and code_map.get("files"):
        payload["app_routes"] = code_map.get("routes", [])
        payload["page_source"] = code_map["files"]   # ground truth for routes/strings/states
    user = json.dumps(payload, indent=2)
    msg = client.messages.create(
        model=s.agent_model,
        # Scale headroom to the budget (~300 output tokens/scenario) so a large
        # ask (full-fledged greenfield ~20) isn't truncated mid-JSON → empty parse.
        max_tokens=min(16000, 1500 + budget * 350),
        system=[{"type": "text",
                  "text": SYSTEM + (_AUTH_DATA_RULE if s.test_data_enabled else ""),
                  "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   f"{goal}\n\nPropose up to {budget} new scenarios as strict JSON.\n\n{user}"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _parse_json_array(text)


def _parse_json_array(text: str) -> list[dict]:
    start = text.find("[")
    if start == -1:
        return []
    frag = text[start:]
    end = frag.rfind("]")
    if end != -1:
        try:
            data = json.loads(frag[:end + 1])
            if isinstance(data, list):
                return [o for o in data if isinstance(o, dict)]
        except json.JSONDecodeError:
            pass
    # Salvage a truncated array (output hit the token ceiling): keep every
    # complete {...} object, drop the partial trailing one.
    return _salvage_objects(frag)


def _salvage_objects(frag: str) -> list[dict]:
    out: list[dict] = []
    depth, obj_start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(frag):
        if in_str:
            if esc:        esc = False
            elif ch == "\\": esc = True
            elif ch == '"':  in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and obj_start is not None:
                    try:
                        out.append(json.loads(frag[obj_start:i + 1]))
                    except json.JSONDecodeError:
                        pass
                    obj_start = None
    return [o for o in out if isinstance(o, dict)]


# --------------------------------------------------------------------------- #
# Universal risk signals (not domain nouns): anything touching identity, money,
# data destruction, or privileged access is HIGH regardless of the app's domain.
_CRIT = (
    ("HIGH", ("login", "logout", "register", "sign in", "sign up", "auth", "password",
              "account", "payment", "delete", "remove", "destroy", "admin", "permission",
              "security", "token", "credential")),
    ("MEDIUM", ("search", "filter", "sort", "create", "add", "edit", "update", "submit",
                "upload", "form", "save")),
)


def _criticality(text: str) -> str:
    t = text.lower()
    for level, kws in _CRIT:
        if any(k in t for k in kws):
            return level
    return "LOW"


def _heuristic(profile, existing, crawl, target_url, budget, mode, covered) -> list[dict]:
    """No-LLM fallback: derive scenarios from live forms + nav links. In gap-fill
    mode, skip features the existing tests already cover; in greenfield, also emit
    a negative-path scenario per form."""
    from . import gate_service
    covered_lc = {c.lower() for c in covered}
    out: list[dict] = []

    def _skip(text: str) -> bool:
        # In gap-fill, skip any flow whose text overlaps an area the existing
        # tests already cover (keyword match — robust to which token "won" the
        # feature label). Greenfield (covered empty / few tests) never skips.
        if mode != "gapfill":
            return False
        blob = text.lower()
        return any(c in blob for c in covered_lc)

    for form in crawl.get("forms", []):
        action = form.get("action") or target_url
        fields = ", ".join(form.get("inputs", [])[:6]) or "the fields"
        label = action.rstrip("/").split("/")[-1] or "form"
        feature = gate_service.feature_of(action + " " + fields)
        if _skip(action + " " + fields):
            continue
        crit = _criticality(action + " " + fields)
        out.append({
            "title": f"Submit the {label} form",
            "objective": (f"Open {action} , fill {fields}, and submit the form; "
                          f"confirm a success state or result appears. Do not browse elsewhere."),
            "expected": "Form submits and a confirmation/result is shown",
            "feature": feature, "scenario_type": "HAPPY",
            "criticality": crit,
            "rationale": "Live form not covered by existing tests",
        })
        # Greenfield (or any gap on a critical feature): add a negative path too.
        if mode == "greenfield" or crit == "HIGH":
            out.append({
                "title": f"Submit the {label} form with invalid/empty input",
                "objective": (f"Open {action} , submit the form leaving required "
                              f"fields empty or invalid; confirm a validation error is "
                              f"shown and submission is blocked. Do not browse elsewhere."),
                "expected": "A validation error is displayed and the form does not submit",
                "feature": feature, "scenario_type": "NEGATIVE",
                "criticality": crit,
                "rationale": "Negative/validation path for a live form",
            })

    for link in crawl.get("links", []):
        text, href = link["text"], link["href"]
        feature = gate_service.feature_of(text + " " + href)
        if len(text) < 3 or _skip(text + " " + href):
            continue
        out.append({
            "title": f"Navigate to '{text}'",
            "objective": (f"Open {href} and confirm the '{text}' page loads with its "
                          f"main content visible. Do not browse elsewhere."),
            "expected": f"The '{text}' page renders its primary content",
            "feature": feature, "scenario_type": "HAPPY",
            "criticality": _criticality(text),
            "rationale": "Reachable page not covered by existing tests",
        })

    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    type_rank = {"HAPPY": 0, "NEGATIVE": 1, "EDGE": 2}
    out.sort(key=lambda x: (rank.get(x["criticality"], 3), type_rank.get(x["scenario_type"], 3)))
    return out
