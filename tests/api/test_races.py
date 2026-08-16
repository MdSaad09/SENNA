"""GET /races/{year}/{round} over seeded ingest rows: the replay payload for the real
view, read straight from the flagged-superset tables (5.3.4).
"""

import os

import pytest

from tests.api.conftest import RACE_NAME, RACE_ROUND, RACE_SEASON, seed_2024_bahrain

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
    ),
]


def test_race_detail_reads_back_the_ingested_race(client, fresh_schema):
    seed_2024_bahrain()

    detail = client.get(f"/api/v1/races/{RACE_SEASON}/{RACE_ROUND}").json()
    assert detail["year"] == RACE_SEASON
    assert detail["round"] == RACE_ROUND
    assert detail["event_name"] == RACE_NAME

    winner = next(row for row in detail["results"] if row["driver_abbrev"] == "VER")
    assert winner["position"] == 1
    assert winner["points"] == 25.0
    assert detail["laps"]  # a replay needs per-lap rows, not just the classification
    assert all(lap["lap_time_s"] for lap in detail["laps"])


def test_an_unknown_race_is_a_404(client, fresh_schema):
    assert client.get("/api/v1/races/2031/9").status_code == 404
