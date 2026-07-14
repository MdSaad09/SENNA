import pandas as pd
from senna.data.fastf1_loader import plan_sessions

SESSIONS_TO_INGEST = ["Race", "Sprint"]  # fastf1.sessions_to_ingest (E-11: types, not names)


def _event_row(round_number, event_name, event_format, session_names):
    first_day = pd.Timestamp("2024-03-01") + pd.Timedelta(days=14 * (round_number - 1))
    row = {
        "RoundNumber": round_number,
        "EventName": event_name,
        "EventFormat": event_format,
        "EventDate": first_day + pd.Timedelta(days=2),
    }
    for slot, session_name in enumerate(session_names, start=1):
        row[f"Session{slot}"] = session_name
        row[f"Session{slot}DateUtc"] = first_day + pd.Timedelta(hours=6 * slot)
    return row


def _schedule() -> pd.DataFrame:
    # shaped like fastf1.get_event_schedule output; sprint naming changed between
    # 2023 ("Sprint Shootout") and 2024+ ("Sprint Qualifying") — E-11
    return pd.DataFrame(
        [
            _event_row(
                1,
                "Bahrain Grand Prix",
                "conventional",
                ["Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race"],
            ),
            _event_row(
                4,
                "Azerbaijan Grand Prix",
                "sprint_shootout",
                ["Practice 1", "Qualifying", "Sprint Shootout", "Sprint", "Race"],
            ),
            _event_row(
                5,
                "Miami Grand Prix",
                "sprint_qualifying",
                ["Practice 1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"],
            ),
        ]
    )


def test_sprint_weekends_of_both_naming_eras_yield_exactly_race_and_sprint():
    planned = plan_sessions(_schedule(), SESSIONS_TO_INGEST)

    by_round: dict[int, list[str]] = {}
    for entry in planned:
        by_round.setdefault(entry["round"], []).append(entry["session_name"])

    assert by_round[1] == ["Race"]
    assert sorted(by_round[4]) == ["Race", "Sprint"]
    assert sorted(by_round[5]) == ["Race", "Sprint"]
    assert set(by_round) == {1, 4, 5}


def test_planned_sessions_carry_season_agnostic_keys_and_slot_matched_dates():
    schedule = _schedule()

    planned = plan_sessions(schedule, SESSIONS_TO_INGEST)

    for entry in planned:
        assert set(entry) == {"round", "event_name", "session_name", "session_date_utc"}

    # the Sprint sits in a different slot each era; the date must follow the name
    shootout_row = schedule[schedule["RoundNumber"] == 4].iloc[0]
    sprint = next(e for e in planned if e["round"] == 4 and e["session_name"] == "Sprint")
    assert sprint["event_name"] == "Azerbaijan Grand Prix"
    assert sprint["session_date_utc"] == shootout_row["Session4DateUtc"]
