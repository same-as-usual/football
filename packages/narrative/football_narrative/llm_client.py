"""LLMClient seam — Claude when credentials exist, deterministic template otherwise.

The provider is swappable behind `generate_narrative()`; nothing else in the
codebase knows which backend produced the prose.
"""
from __future__ import annotations

import os
from typing import Any, Protocol

from .wordaliser import SYSTEM_PROMPT, build_prompt

CLAUDE_MODEL = "claude-opus-4-8"


class LLMClient(Protocol):
    def narrate(self, facts: dict[str, Any]) -> str: ...


class AnthropicNarrator:
    """Claude Messages API implementation (adaptive thinking)."""

    def narrate(self, facts: dict[str, Any]) -> str:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(facts)}],
        )
        return next(b.text for b in response.content if b.type == "text")


class TemplateNarrator:
    """Deterministic fallback — pure facts, zero hallucination risk, no API cost."""

    def narrate(self, facts: dict[str, Any]) -> str:
        home, away = facts["home"], facts["away"]
        hs, as_ = facts["finalScore"]
        xg = facts["xg"]
        paras: list[str] = []

        verdict = "a draw" if hs == as_ else f"a win for {home if hs > as_ else away}"
        paras.append(
            f"{home} {hs}–{as_} {away} in the {facts['competition']} ({facts['season']}) — "
            f"{verdict}. {home} produced {facts['shotCounts'][home]} shots worth {xg[home]} xG; "
            f"{away} managed {facts['shotCounts'][away]} shots worth {xg[away]} xG."
        )

        if facts["goals"]:
            goal_bits = [
                f"{g['player']} ({g['team']}, {g['minute']}′, xG {g['xg']:.2f})"
                for g in facts["goals"]
            ]
            paras.append("Goals: " + "; ".join(goal_bits) + ".")
        if facts.get("penaltyShootout"):
            p = facts["penaltyShootout"]
            paras.append(
                f"It went all the way: after extra time, the shootout finished "
                f"{home} {p[home]}–{p[away]} {away}."
            )
        if facts["bigMissedChances"]:
            m = facts["bigMissedChances"][0]
            paras.append(
                f"The biggest chance that got away: {m['player']} ({m['team']}) with a "
                f"{m['xg']:.2f}-xG opportunity in the {m['minute']}′ that ended "
                f"{m['outcome'].replace('_', ' ')}."
            )

        gap = round(abs(xg[home] - xg[away]), 2)
        better = home if xg[home] > xg[away] else away
        paras.append(
            f"On the balance of chances, {better} edged the underlying numbers by {gap} xG"
            + (" — the scoreline flattered the other side." if
               (better == home) != (hs > as_) and hs != as_ else ".")
        )
        return "\n\n".join(paras)


def get_narrator() -> LLMClient:
    """Claude if credentials are configured; deterministic template otherwise."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return AnthropicNarrator()
    return TemplateNarrator()


def generate_narrative(facts: dict[str, Any]) -> dict[str, Any]:
    narrator = get_narrator()
    backend = type(narrator).__name__
    try:
        text = narrator.narrate(facts)
    except Exception:
        if isinstance(narrator, TemplateNarrator):
            raise
        text = TemplateNarrator().narrate(facts)  # graceful degradation
        backend = "TemplateNarrator(fallback)"
    return {"text": text, "backend": backend, "attribution": facts["attribution"]}
