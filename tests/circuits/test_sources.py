from senna.circuits.sources import pick_most_recent_dry


def test_pick_most_recent_dry_prefers_latest_dry():
    sessions = [
        {
            "round": 1,
            "session_date_utc": "2026-03-08",
            "is_dry": True,
            "event_name": "Bahrain Grand Prix",
        },
        {
            "round": 5,
            "session_date_utc": "2026-05-24",
            "is_dry": True,
            "event_name": "Spanish Grand Prix",
        },
        {
            "round": 7,
            "session_date_utc": "2026-06-28",
            "is_dry": False,
            "event_name": "Austrian Grand Prix",
        },
    ]

    chosen = pick_most_recent_dry(sessions)

    assert chosen["event_name"] == "Spanish Grand Prix"


def test_pick_returns_none_when_all_wet():
    sessions = [
        {
            "season": 2026,
            "round": 3,
            "session_date_utc": "2026-04-12",
            "is_dry": False,
            "event_name": "Japanese Grand Prix",
        },
        {
            "season": 2026,
            "round": 6,
            "session_date_utc": "2026-06-07",
            "is_dry": False,
            "event_name": "Canadian Grand Prix",
        },
    ]

    assert pick_most_recent_dry(sessions) is None
