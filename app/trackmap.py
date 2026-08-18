"""The stylised track loop and the field's place on it.

The environment is lap-quantised and holds no geometry; s_track is the serve
layer's display-only synthesis of each car's lap fraction (frames.py), and this
module gives it somewhere to be drawn: a stadium loop whose proportions are a
visual choice, not a circuit's. Every view that draws it says so on screen (F11).
"""

import math

from app import theme

# stylised — loop proportions only; no circuit geometry is claimed anywhere
STRAIGHT = 2.2
RADIUS = 0.75

_PERIMETER = 2 * STRAIGHT + 2 * math.pi * RADIUS


def loop_point(s: float) -> tuple[float, float]:
    """The point a lap fraction s maps to, walking the loop from the start line.

    The start sits at the top straight's left end and the walk runs clockwise:
    top straight, right arc, bottom straight, left arc — so the leader crossing
    the line (s = 0) reads left-to-right the way a timing screen does."""
    d = (s % 1.0) * _PERIMETER
    half = STRAIGHT / 2
    if d < STRAIGHT:  # top straight, left to right
        return -half + d, RADIUS
    d -= STRAIGHT
    if d < math.pi * RADIUS:  # right arc, down
        angle = d / RADIUS
        return half + math.sin(angle) * RADIUS, math.cos(angle) * RADIUS
    d -= math.pi * RADIUS
    if d < STRAIGHT:  # bottom straight, right to left
        return half - d, -RADIUS
    d -= STRAIGHT
    angle = d / RADIUS  # left arc, up
    return -half - math.sin(angle) * RADIUS, -math.cos(angle) * RADIUS


def outline(points: int = 200) -> list[dict]:
    return [dict(zip(("x", "y"), loop_point(i / points))) for i in range(points + 1)]


def field_rows(frame: dict) -> list[dict]:
    """One row per car at this lap: position on the loop, team identity, seat shape.

    Identity is never colour alone — the label rides every dot, the teammate seat
    is hollow, and the ego carries the aqua ring — because the team palette has
    known near pairs (the two blues, silver and white) by its own reference sheet."""
    rows = []
    for car in frame["cars"]:
        x, y = loop_point(car["s_track"])
        name, colour, is_teammate = theme.team_of(car["id"])
        rows.append({
            "x": x, "y": y,
            "car": theme.car_label(car["id"]),
            "team": name,
            "colour": colour,
            "seat": "teammate" if is_teammate else "primary",
            "ego": car["id"] == 0,
            "position": car["position"],
            "compound": car["compound"],
            "tyre_age": car["tyre_age"],
            "in_pit": car["in_pit"],
        })
    return rows
