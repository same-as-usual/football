"""Normalize StatsBomb-shaped events into canonical display coordinates.

Display coords: stable pitch, home attacks +x in period 1, teams swap at HT.
Model coords (used by xT/xG): each acting team always attacks +x.
"""
from __future__ import annotations

from typing import Any

from football_core.coords import statsbomb_to_canonical

KEPT_TYPES = {"Pass", "Carry", "Shot", "Ball Recovery", "Interception", "Clearance",
              "Duel", "Foul Committed", "Goal Keeper", "Dribble", "Miscontrol"}


def parse_ts_ms(timestamp: str) -> int:
    """'HH:MM:SS.mmm' (per-period clock) -> ms."""
    hh, mm, rest = timestamp.split(":")
    ss, ms = rest.split(".") if "." in rest else (rest, "0")
    return ((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000 + int(ms.ljust(3, "0")[:3])


def attacking_right(is_home: bool, period: int) -> bool:
    """Home attacks +x in odd periods; away in even periods."""
    return is_home == (period % 2 == 1)


def to_display(loc: list[float] | None, is_home: bool, period: int) -> tuple[float, float] | None:
    """StatsBomb attacking-direction location -> stable display coords."""
    if not loc:
        return None
    cx, cy = statsbomb_to_canonical(loc[0], loc[1])
    if not attacking_right(is_home, period):
        cx, cy = -cx, -cy
    return round(cx, 2), round(cy, 2)


def end_location(ev: dict[str, Any]) -> list[float] | None:
    t = ev["type"]["name"]
    if t == "Pass":
        return ev.get("pass", {}).get("end_location")
    if t == "Carry":
        return ev.get("carry", {}).get("end_location")
    if t == "Shot":
        el = ev.get("shot", {}).get("end_location")
        return el[:2] if el else None
    return None


def event_outcome(ev: dict[str, Any]) -> str | None:
    t = ev["type"]["name"]
    if t == "Pass":
        return "incomplete" if ev.get("pass", {}).get("outcome") else "complete"
    if t == "Shot":
        return (ev.get("shot", {}).get("outcome", {}) or {}).get("name", "").lower().replace(" ", "_") or None
    if t == "Duel":
        return (ev.get("duel", {}).get("outcome", {}) or {}).get("name")
    return None
