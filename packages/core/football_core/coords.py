"""Canonical pitch coordinate system.

Meters. Pitch 105 x 68. Origin at center. +x = attacking right, +y = up.
All adapters MUST transform provider coordinates into this system.
"""

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

GOAL_WIDTH = 7.32
GOAL_CENTER_RIGHT = (PITCH_LENGTH / 2, 0.0)  # goal being attacked when moving +x


def statsbomb_to_canonical(x: float, y: float) -> tuple[float, float]:
    """StatsBomb: 120x80, origin top-left, y down -> canonical meters."""
    cx = (x / 120.0 - 0.5) * PITCH_LENGTH
    cy = (0.5 - y / 80.0) * PITCH_WIDTH
    return round(cx, 2), round(cy, 2)
