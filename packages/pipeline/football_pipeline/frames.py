"""Reconstruct sparse replay keyframes from events + 360 freeze-frames.

Event-plane replay is honest about its nature: interpolated=True.
Ball path: keyframe at each on-ball event start, plus an end-of-move keyframe
using the event's duration. Player dots come from 360 freeze-frames (anonymous:
teammate/opponent/keeper/actor flags only — no player identity in StatsBomb 360).
"""
from __future__ import annotations

from typing import Any

from football_core.model import FrameChunk, Keyframe, PlayerDot, Point

from .normalize import attacking_right, parse_ts_ms, to_display

ON_BALL = {"Pass", "Carry", "Shot", "Ball Recovery", "Interception", "Clearance", "Dribble", "Goal Keeper"}


def build_keyframes(
    events: list[dict[str, Any]],
    frames_360: list[dict[str, Any]],
    home_team_id: int,
) -> FrameChunk:
    ff_by_event = {f["event_uuid"]: f for f in frames_360}
    keyframes: list[Keyframe] = []

    for ev in events:
        if ev["type"]["name"] not in ON_BALL or not ev.get("location"):
            continue
        period = ev["period"]
        is_home = ev["team"]["id"] == home_team_id
        t = parse_ts_ms(ev["timestamp"])
        start = to_display(ev["location"], is_home, period)
        if start is None:
            continue

        players: list[PlayerDot] = []
        ff = ff_by_event.get(ev["id"])
        if ff:
            for p in ff.get("freeze_frame", []):
                dot = to_display(p["location"], is_home, period)
                if dot is None:
                    continue
                players.append(PlayerDot(
                    x=dot[0], y=dot[1],
                    team=("home" if is_home else "away") if p["teammate"] else ("away" if is_home else "home"),
                    keeper=bool(p.get("keeper")),
                    actor=bool(p.get("actor")),
                ))

        keyframes.append(Keyframe(
            t=t, period=period, ball=Point(x=start[0], y=start[1]),
            players=players, eventRef=ev["id"],
        ))

        # end-of-move ball keyframe (pass/carry/shot destinations)
        from .normalize import end_location
        end = end_location(ev)
        dur = ev.get("duration") or 0
        if end and dur:
            e = to_display(end, is_home, period)
            if e:
                keyframes.append(Keyframe(
                    t=t + int(dur * 1000), period=period,
                    ball=Point(x=e[0], y=e[1]), players=[], eventRef=None,
                ))

    keyframes.sort(key=lambda k: (k.period, k.t))
    return FrameChunk(interpolated=True, frameRateHz=None, keyframes=keyframes)
