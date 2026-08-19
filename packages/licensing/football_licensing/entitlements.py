"""Entitlements boundary — freemium paywall slot.

Free build: allow-all stub. Commercial build: real plan checks slot in here
(Stripe/billing behind this interface) with zero re-plumbing elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entitlements:
    plan: str = "free"

    def can(self, feature: str) -> bool:  # noqa: ARG002 — allow-all stub
        return True


def resolve_entitlements(user_token: str | None = None) -> Entitlements:  # noqa: ARG001
    """Free build: everyone gets the free plan with all current features."""
    return Entitlements(plan="free")


COMMERCIAL_BUILD = False  # flip in commercial deployments; publish() enforces policy
