from __future__ import annotations

import json
import re
import secrets

from ..config import get_settings


TESTDATA_SYSTEM = (
    "You generate realistic, disposable QA test data for end-to-end UI testing of a "
    "web app. Given the app's profile and the input fields seen on its live pages, "
    "return ONE JSON object a tester would use to sign up / log in and fill forms. "
    "Keys: name (a person's full name), email (a plausible address), url (a valid "
    "http(s) URL usable in any URL/link field). STRICT JSON only — no prose, no fences."
)


def generate_test_data(profile: dict, crawl: dict, target_url: str) -> dict:
    """Generate run-unique, app-appropriate throwaway test data via the LLM.

    Best-practice guards: the password is always a strong code-generated value and
    the email is always forced run-unique + valid (never trust the model for those),
    while the model supplies realistic name/url tailored to the app's real fields.
    Falls back to safe defaults when no Anthropic key is set or the call fails —
    test-data generation must never break a run."""
    settings = get_settings()
    token = secrets.token_hex(4)
    gen: dict = {}
    if settings.anthropic_api_key:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings.anthropic_api_key)
            fields = sorted({i for f in crawl.get("forms", [])
                             for i in f.get("inputs", [])})[:20]
            payload = {"target_url": target_url,
                       "frameworks": profile.get("frameworks", []),
                       "input_fields_seen": fields}
            msg = client.messages.create(
                model=settings.agent_model, max_tokens=300,
                system=[{"type": "text", "text": TESTDATA_SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content":
                           "Generate test data as strict JSON.\n\n" + json.dumps(payload)}],
            )
            text = "".join(b.text for b in msg.content if b.type == "text")
            a, b = text.find("{"), text.rfind("}")
            if a != -1 and b != -1:
                gen = json.loads(text[a:b + 1])
        except Exception:  # noqa: BLE001 — never let test-data gen break a run
            gen = {}
    name = (str(gen.get("name") or "Kane TestPilot").strip() or "Kane TestPilot")[:60]
    url = str(gen.get("url") or "https://example.com").strip() or "https://example.com"
    # Force a run-unique, valid email (don't trust the model for uniqueness).
    base = re.sub(r"[^a-z0-9.]+", "", str(gen.get("email", "")).split("@")[0].lower()) \
        or "kane.testpilot"
    email = f"{base}.{token}@example.com"
    # Always a strong, policy-friendly password (upper, lower, digit, symbol).
    password = f"Kn{secrets.token_urlsafe(8)}9!"
    return {"name": name, "email": email, "password": password, "url": url}


def _clean(text: str) -> str:
    """Strip markdown code fences so the result is runnable Python."""
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()

SYNTH_SYSTEM = (
    "You are a senior SDET. Turn a Kane-verified browser trace into ONE clean, "
    "deterministic Playwright-Python pytest test. Use resilient locators, add explicit "
    "assertions tied to the expected result, no async/await (sync Playwright). "
    "Return ONLY the test function code."
)


def synthesize(objective: str, expected: str, kane_steps: list[str], kane_code: str) -> str:
    """Synthesize a clean asserted test from Kane's real trace (Claude API)."""
    settings = get_settings()
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.agent_model,
        max_tokens=1500,
        system=[{"type": "text", "text": SYNTH_SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": (
            f"Objective: {objective}\nExpected result: {expected}\n"
            f"Kane steps:\n- " + "\n- ".join(kane_steps) +
            f"\n\nKane-exported Playwright body:\n{kane_code}"
        )}],
    )
    return _clean("".join(b.text for b in msg.content if b.type == "text"))


def repair(code: str, error: str, kane_steps: list[str]) -> str:
    """Repair a failing test grounded in the real error + Kane trace."""
    settings = get_settings()
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.agent_model,
        max_tokens=1500,
        system=[{"type": "text", "text": SYNTH_SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": (
            f"This test failed:\n{code}\n\nError:\n{error}\n\n"
            f"Real Kane trace:\n- " + "\n- ".join(kane_steps) +
            "\nFix it. Return ONLY the corrected test function."
        )}],
    )
    return _clean("".join(b.text for b in msg.content if b.type == "text"))
