

EGO = 0  # the agent's car id, the F10 CarState contract

_EVENT_RANK = ("red", "sc", "vsc", "weather")
_EVENT_PHRASE = {
    "red": "a lap-{lap} red flag",
    "sc": "a lap-{lap} safety car",
    "vsc": "a lap-{lap} virtual safety car",
    "weather": "lap-{lap} weather",
}
_COUNTS = {0: "no stops", 1: "one stop", 2: "two stops", 3: "three stops"}


def race_headline(frames: list[dict], summary: dict, grid_position: int | None) -> str:
    start = f"P{grid_position}" if grid_position else "—"  # a run row can lack its grid
    finish = "DNF" if summary.get("dnf") else f"P{summary.get('final_position')}"
    stops = len(_ego_stops(frames))
    parts = [f"{start} → {finish}", _COUNTS.get(stops, f"{stops} stops")]
    headliner = _headline_event(frames)
    if headliner is not None:
        kind, lap = headliner
        parts.append(f"through {_EVENT_PHRASE[kind].format(lap=lap)}")
    return " · ".join(parts)


def race_moments(frames: list[dict]) -> list[dict]:
  
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
