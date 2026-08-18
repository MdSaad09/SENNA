"""The race headline and moments strip are template assembly over stored frames.

No text generation anywhere: given the same frames and summary, the same sentence comes
out. These tests pin the template's obligations — start position, finish or DNF, stop
count, and the single most significant event (red > sc > vsc > weather) — and pin that
the moments strip reports every stored event once, in lap order, with the ego's stops
and nobody else's.
"""

from app.story import race_headline, race_moments

EGO = 0
GRID = 8


def _frame(lap: int, *, ego_position: int = 2, ego_compound: str = "MEDIUM",
           ego_in_pit: bool = False, events: list | None = None,
           rival_in_pit: int | None = None) -> dict:
    field = [p for p in range(1, 23) if p != ego_position]
    cars = [{
        "id": EGO, "s_track": 0.0, "position": ego_position,
        "compound": ego_compound, "tyre_age": 3, "gap_ahead_s": None,
        "in_pit": ego_in_pit,
    }]
    for car in range(1, 22):
        cars.append({
            "id": car, "s_track": 0.0, "position": field[car - 1],
            "compound": "HARD", "tyre_age": 5, "gap_ahead_s": 1.2,
            "in_pit": car == rival_in_pit,
        })
    return {
        "lap": lap,
        "cars": cars,
        "agent": {"soc_mj": 2.4, "harvest_mj": 3.1, "deploy_mj": 3.0, "mode": 1,
                  "action": {"pit": 0, "mode": 1},
                  "reward_terms": {"pace": 0.0, "position": 0.0, "terminal": 0.0,
                                   "total": 0.0},
                  "mask_reasons": {}},
        "events": events or [],
    }


def _event(kind: str, detail: str | None = None) -> dict:
    return {"kind": kind, "car_id": None, "detail": detail}


def _one_stop_race(laps: int = 30, pit_lap: int = 16,
                   events_by_lap: dict | None = None) -> list[dict]:
    """MEDIUM to HARD at pit_lap; the pit-lap frame already carries the new compound,
    matching how the serve layer stores frames."""
    events_by_lap = events_by_lap or {}
    return [
        _frame(lap,
               ego_compound="MEDIUM" if lap < pit_lap else "HARD",
               ego_in_pit=lap == pit_lap,
               events=events_by_lap.get(lap))
        for lap in range(1, laps + 1)
    ]


def _summary(final_position: int = 2, dnf: bool = False, laps: int = 30) -> dict:
    return {"final_position": final_position, "dnf": dnf, "total_laps": laps,
            "race_time_s": 5400.0, "nominal_lap_s": 95.0}


def test_a_clean_one_stop_race_reads_start_finish_and_stop_count():
    headline = race_headline(_one_stop_race(), _summary(final_position=2), GRID)
    assert "P8" in headline
    assert "P2" in headline
    assert "one stop" in headline.lower() or "1 stop" in headline.lower()


def test_a_clean_race_headline_mentions_no_event():
    headline = race_headline(_one_stop_race(), _summary(), GRID)
    lowered = headline.lower()
    for word in ("safety car", "red", "vsc", "rain", "weather"):
        assert word not in lowered, f"clean race headline invented an event: {word!r}"


def test_a_dnf_headline_says_dnf_instead_of_a_finishing_position():
    # summary still carries the frozen classification; the headline must not use it
    headline = race_headline(_one_stop_race(), _summary(final_position=18, dnf=True), GRID)
    assert "DNF" in headline
    assert "P8" in headline
    assert "P18" not in headline
    assert "one stop" in headline.lower() or "1 stop" in headline.lower()


def test_a_safety_car_race_names_the_event_and_its_lap():
    frames = _one_stop_race(laps=35, events_by_lap={30: [_event("sc")]})
    headline = race_headline(frames, _summary(laps=35), GRID)
    assert "safety car" in headline.lower()
    assert "30" in headline


def test_a_red_flag_outranks_a_safety_car_in_the_headline():
    frames = _one_stop_race(laps=35, events_by_lap={12: [_event("sc")],
                                                    20: [_event("red")]})
    headline = race_headline(frames, _summary(laps=35), GRID)
    assert "red" in headline.lower()


def test_a_safety_car_outranks_weather_in_the_headline():
    frames = _one_stop_race(laps=35, events_by_lap={8: [_event("weather", "rain")],
                                                    30: [_event("sc")]})
    headline = race_headline(frames, _summary(laps=35), GRID)
    assert "safety car" in headline.lower()
    assert "rain" not in headline.lower()


def test_a_zero_stop_race_says_so():
    frames = [_frame(lap, ego_position=5) for lap in range(1, 31)]
    headline = race_headline(frames, _summary(final_position=5), 5)
    lowered = headline.lower()
    assert any(said in lowered for said in ("no stop", "zero stop", "0 stop")), headline


def test_moments_report_every_stored_event_once_in_lap_order():
    frames = _one_stop_race(laps=35, pit_lap=20,
                            events_by_lap={5: [_event("weather", "rain")],
                                           12: [_event("sc")],
                                           30: [_event("vsc")]})
    moments = race_moments(frames)
    assert [m["lap"] for m in moments] == sorted(m["lap"] for m in moments)
    kinds_at = {(m["lap"], m["kind"]) for m in moments}
    assert (5, "weather") in kinds_at
    assert (12, "sc") in kinds_at
    assert (30, "vsc") in kinds_at
    assert len(moments) == len(kinds_at), "an event was reported more than once"


def test_moments_carry_lap_kind_and_detail():
    frames = _one_stop_race(laps=35, events_by_lap={12: [_event("sc")]})
    for moment in race_moments(frames):
        assert {"lap", "kind", "detail"} <= set(moment)


def test_the_egos_stop_is_a_pit_moment_with_the_new_compound():
    moments = race_moments(_one_stop_race(pit_lap=16))
    stops = [m for m in moments if m["kind"] == "pit"]
    assert len(stops) == 1
    assert stops[0]["lap"] == 16
    assert "HARD" in stops[0]["detail"]


def test_rival_pit_stops_are_not_moments():
    frames = [_frame(lap, rival_in_pit=7 if lap == 9 else None)
              for lap in range(1, 31)]
    moments = race_moments(frames)
    assert not [m for m in moments if m["kind"] == "pit"], \
        "a rival's stop leaked into the ego's moments"
