from __future__ import annotations

import re

from ..config import get_settings


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
