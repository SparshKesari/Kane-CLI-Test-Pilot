from __future__ import annotations

import re

from ..models import ExistingTest

_STOP = set("a an the to and or of on in at for with from is are be that this it its "
           "as by user can should when then verify confirm open click page test".split())
_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def _has_concrete_assertion(expected: str) -> bool:
    """A concrete assertion names a specific value: a quoted string, a URL, a
    number, or an explicit CONTAINS/equals check — not a vague 'expected name'."""
    e = expected.lower()
    if re.search(r"['\"][^'\"]{2,}['\"]", expected):      # quoted literal
        return True
    if re.search(r"https?://|/\w|\b\d+\b", expected):     # url/path/number
        return True
    if any(k in e for k in ("contains", "equals", "displays", "shows", "visible", "remains")):
        return True
    return False


# Feature attribution is DERIVED from the app under test — never a fixed domain
# vocabulary — so this works for any project (a TODO app, a wiki, a dashboard,
# a storefront, anything). The LLM strategist assigns each scenario's `feature`
# from the live UI; here we only extract salient route/keyword tokens from the
# EXISTING tests so the gap-fill prompt knows what's already covered.
_TEST_NOISE = set(
    "test tests spec specs should it describe context when then given page pages "
    "view views screen www http https com index php html htm aspx jsp route path "
    "the and for with from into onto get post put able new old tmp e2e ui app".split())


def _salient(text: str) -> list[str]:
    """App-derived keywords: identifier-ish tokens (route/feature names) minus
    generic test/URL noise, longest first so distinctive terms win."""
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower())
    seen, out = set(), []
    for t in toks:
        if t in _TEST_NOISE or t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    out.sort(key=len, reverse=True)
    return out


def feature_of(text: str) -> str:
    """A feature label derived from the text's own most-distinctive token
    (e.g. a route segment). Domain-agnostic — no hardcoded vocabulary."""
    sal = _salient(text)
    return sal[0].upper() if sal else "GENERAL"


def coverage_of(existing: list[ExistingTest]) -> list[str]:
    """Salient keywords/areas the repo's existing tests already exercise, mined
    from their names/targets/files. Free-form (not a fixed taxonomy) and fed to
    the gap-fill strategist alongside the full existing-test list so the LLM —
    which is far better at this than a keyword map — decides what's missing."""
    feats: set[str] = set()
    for t in existing:
        feats.update(_salient(f"{t.name} {t.target} {t.file}")[:3])
    return sorted(feats)[:20]


def filter_scenarios(
    scenarios: list[dict],
    existing: list[ExistingTest],
    crawl: dict,
    *,
    dedup_existing: float = 0.5,
    dedup_self: float = 0.6,
) -> tuple[list[dict], list[dict]]:
    """Return (kept, dropped). Drops: duplicates of existing tests, near-duplicate
    proposals, and trivially-asserted scenarios. Kept list is ranked by criticality."""
    existing_tok = [_tokens(f"{t.name} {t.target}") for t in existing]
    kept: list[dict] = []
    dropped: list[dict] = []
    kept_tok: list[set[str]] = []

    for sc in sorted(scenarios, key=lambda s: _RANK.get(s.get("criticality", "MEDIUM"), 1)):
        tok = _tokens(f"{sc.get('title','')} {sc.get('objective','')}")

        dup_ex = max((_jaccard(tok, e) for e in existing_tok), default=0.0)
        if dup_ex >= dedup_existing:
            dropped.append({**sc, "drop_reason": f"already covered by an existing test (sim {dup_ex:.2f})"})
            continue
        dup_self = max((_jaccard(tok, k) for k in kept_tok), default=0.0)
        if dup_self >= dedup_self:
            dropped.append({**sc, "drop_reason": f"near-duplicate of a kept scenario (sim {dup_self:.2f})"})
            continue
        if not _has_concrete_assertion(sc.get("expected", "")):
            dropped.append({**sc, "drop_reason": "no concrete/observable assertion"})
            continue

        kept.append(sc)
        kept_tok.append(tok)

    return kept, dropped


# --------------------------------------------------------------------------- #
# Post-Kane quality gates — applied in P6 AFTER a scenario passes Kane, BEFORE
# the test is accepted into the suite. These exist to prevent "false greens":
# a committed test that goes green without actually validating the behavior.
# (A real failure mode we've seen: a flow fails live verification, yet the test
# still goes green because it fell back to a body with tautological assertions
# like `count() >= 0`.)
# --------------------------------------------------------------------------- #

# Assertions that are always true (or nearly so) and prove nothing.
_TAUTOLOGY = re.compile(
    r"""\.count\(\)\s*(>=\s*0|>\s*-1|>=\s*-1)      # locator.count() >= 0  → always true
        | \bassert\s+(True|1)\b                     # assert True / assert 1
        | \bassert\s+not\s+(False|0)\b              # assert not False
        | \.count\(\)\s*==\s*\.count\(\)            # x.count() == x.count()
    """,
    re.X,
)

# Generic "the page exists" markers — fine as preconditions, worthless as the
# ONLY evidence a feature works.
_PAGELOAD = re.compile(r"\b(title|\.url\b|load_state|domcontentloaded)\b"
                       r"|TAG_NAME\s*,\s*['\"](body|html)['\"]", re.I)

# Strong observable signals — reading real state or comparing to a real value.
_STRONG = re.compile(
    r"inner_text|text_content|is_visible|input_value|get_attribute"
    r"|to_have_text|to_contain_text|to_be_visible|to_have_url|to_have_value|to_have_count",
    re.I,
)
# A non-trivial literal (>=2 chars) tied to a comparison — e.g. `in`, `==`, `!=`.
_LITERAL_CMP = re.compile(
    r"""(==|!=|\bin\b|contains)\s*['\"][^'\"]{2,}['\"]   # op then literal
        | ['\"][^'\"]{2,}['\"]\s*(==|!=|\bin\b)          # literal then op
    """,
    re.X,
)
# A count/len strictly greater than zero (>=1, >0) — proves something rendered.
_POSITIVE_COUNT = re.compile(r"(count\(\)|len\([^)]*\))\s*(>=\s*[1-9]|>\s*0)")

_ASSERTISH = re.compile(r"\b(assert|expect)\b")


def _is_meaningful(ln: str) -> bool:
    """True if this single assertion would actually fail when the behavior is
    broken (not a tautology and not a bare page-load check)."""
    if _TAUTOLOGY.search(ln):
        return False
    if _STRONG.search(ln) or _LITERAL_CMP.search(ln) or _POSITIVE_COUNT.search(ln):
        return True
    if _PAGELOAD.search(ln):              # only a load/title/url-exists check
        return False
    return True                            # some other concrete comparison


def assert_quality(code: str) -> tuple[bool, str]:
    """Inspect the ACTUAL generated test body (not the scenario's `expected`
    text) for meaningful assertions. Returns (ok, reason). A test is rejected
    when it has no assertion at all, or every assertion is a tautology / bare
    page-load check — i.e. it would go green even if the feature were broken."""
    assert_lines = [ln.strip() for ln in code.splitlines()
                    if not ln.lstrip().startswith("#") and _ASSERTISH.search(ln)]
    if not assert_lines:
        return False, "test has no assertion — cannot validate behavior"
    if not any(_is_meaningful(ln) for ln in assert_lines):
        return False, ("test only asserts page-load/tautologies "
                       "(e.g. count()>=0, title present) — insufficient for regression")
    return True, ""


# UNIVERSAL web-action verb groups (with morphological variants) — these are
# generic UI actions, NOT domain nouns, so the check works for any app. If the
# objective is about one of these actions, Kane's observed trace must reflect the
# SAME action — otherwise Kane wandered and "succeeded" at the wrong thing
# (objective said one action, the agent performed a different one, yet a green
# test still shipped).
_ACTION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("authenticate", ("login", "log in", "logged", "signin", "sign in", "signed in")),
    ("sign out",     ("logout", "log out", "logged out", "sign out", "signed out")),
    ("register",     ("register", "registration", "sign up", "signup", "create account")),
    ("search",       ("search", "searched", "searching", "query")),
    ("create/add",   ("add", "added", "create", "created", "insert", "new ")),
    ("delete",       ("delete", "deleted", "remove", "removed", "clear")),
    ("update",       ("update", "updated", "edit", "edited", "modify", "change")),
    ("submit",       ("submit", "submitted", "save", "saved", "send", "sent")),
    ("upload",       ("upload", "uploaded", "import")),
    ("sort/filter",  ("sort", "sorted", "filter", "filtered", "refine")),
)


def _stem(tok: str) -> str:
    return re.sub(r"(ing|ed|es|s)$", "", tok)


def intent_match(objective: str, kane_one_liner: str,
                 kane_steps: list[str]) -> tuple[bool, str]:
    """Compare what the scenario INTENDED against what Kane OBSERVED. Returns
    (ok, reason). Domain-agnostic: derives intent from the scenario's own words
    plus universal web-action verbs — no hardcoded feature vocabulary."""
    obj = objective.lower()
    observed = (kane_one_liner + " " + " ".join(kane_steps)).lower()
    if not observed.strip():
        return True, ""  # nothing observed to compare — don't over-block

    obj_actions = {name for name, vs in _ACTION_GROUPS if any(v in obj for v in vs)}
    obs_actions = {name for name, vs in _ACTION_GROUPS if any(v in observed for v in vs)}

    # 1) Kane performed an action the objective named (any morphological variant)
    #    → intent confirmed at the action level. Good enough; don't second-guess.
    if obj_actions & obs_actions:
        return True, ""

    # 2) Kane performed a DIFFERENT named action than the objective asked for
    #    (e.g. objective "add", Kane "deleted") → real drift. Only fires when the
    #    observed trace itself names a competing action — an incidental verb in
    #    the objective that Kane reports with a synonym (objective "submit the
    #    filter", Kane "selected the category") is NOT flagged here; it falls to
    #    the overlap check below, which sees the matching nouns and passes.
    if obj_actions and obs_actions:
        return False, (f"intent drift — objective involves {sorted(obj_actions)} but Kane "
                       f"performed {sorted(obs_actions)}: {kane_one_liner!r}")

    # 3) At least one side names no clear action: fall back to content overlap on
    #    stemmed tokens — overlap-coefficient on the smaller set, so a verbose
    #    objective vs a terse one-liner isn't unfairly penalized.
    ot = {_stem(t) for t in _tokens(obj)}
    bt = {_stem(t) for t in _tokens(observed)}
    if ot and bt:
        overlap = len(ot & bt) / min(len(ot), len(bt))
        if overlap < 0.25:
            return False, (f"intent drift — Kane's trace barely matches the objective "
                           f"(overlap {overlap:.2f}): {kane_one_liner!r}")
    return True, ""
