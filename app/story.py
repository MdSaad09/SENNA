"""The race headline and moments strip — template assembly over stored frames.

Deterministic on purpose: the same frames and summary always produce the same
sentence, the same honesty rule the decision cards follow (5.8.3). The headline
carries where the race started, where it ended, what the stops cost, and the one
event that most shaped it — red flag over safety car over virtual over weather —
and says nothing at all about a race that was clean.
"""

EGO = 0  # the agent's car id, the F10 CarState contract

_EVENT_RANK = ("red", "sc", "vsc", "weather")
_EVENT_PHRASE = {
    "red": "a lap-{lap} red flag",
    "sc": "a lap-{lap} safety car",
    "vsc": "a lap-{lap} virtual safety car",
    "weather": "lap-{lap} weather",
}
_COUNTS = {0: "no stops", 1: "one stop", 2: "two stops", 3: "three stops"}


def race_headline(frames: list[dict], summary: dict, grid_position: int) -> str:
    finish = "DNF" if summary.get("dnf") else f"P{summary.get('final_position')}"
    stops = len(_ego_stops(frames))
    parts = [f"P{grid_position} → {finish}", _COUNTS.get(stops, f"{stops} stops")]
    headliner = _headline_event(frames)
    if headliner is not None:
        kind, lap = headliner
        parts.append(f"through {_EVENT_PHRASE[kind].format(lap=lap)}")
    return " · ".join(parts)


def race_moments(frames: list[dict]) -> list[dict]:
    """Every stored track event once, in lap order, plus the ego's stops and nobody
    else's. Pit events in the stream cover all 22 cars, so stops are read off the
    ego's own in_pit flag instead — the pit-lap frame already carries the new
    compound, which is the detail worth showing."""
    moments = []
    for frame in frames:
        for event in frame.get("events", []):
            if event["kind"] == "pit":
                continue
            moments.append({"lap": frame["lap"], "kind": event["kind"],
                            "detail": event.get("detail")})
    for lap, compound in _ego_stops(frames):
        moments.append({"lap": lap, "kind": "pit", "detail": f"pit for {compound}"})
    return sorted(moments, key=lambda m: m["lap"])


def _ego_stops(frames: list[dict]) -> list[tuple[int, str]]:
    stops = []
    for frame in frames:
        ego = next(car for car in frame["cars"] if car["id"] == EGO)
        if ego["in_pit"]:
            stops.append((frame["lap"], ego["compound"]))
    return stops


def _headline_event(frames: list[dict]) -> tuple[str, int] | None:
    first_lap: dict[str, int] = {}
    for frame in frames:
        for event in frame.get("events", []):
            if event["kind"] in _EVENT_RANK:
                first_lap.setdefault(event["kind"], frame["lap"])
    for kind in _EVENT_RANK:
        if kind in first_lap:
            return kind, first_lap[kind]
    return None
