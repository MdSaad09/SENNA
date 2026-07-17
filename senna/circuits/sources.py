"""Choosing the lap each ribbon is built from (5.10.1 item 1).

The centreline comes from the fastest clean lap of the most recent dry session:
dry so the racing line is not a wet-weather detour, most recent so the ribbon
reflects the current layout. Session dryness is the flag F01 computed at ingest
(Session.is_dry); this module only selects, the FastF1 read lives in senna.data.
"""


def pick_most_recent_dry(sessions: list[dict]) -> dict | None:
    """Latest dry session by UTC date, or None if every candidate ran wet."""
    dry = [session for session in sessions if session.get("is_dry")]
    if not dry:
        return None
    return max(dry, key=lambda session: session["session_date_utc"])
