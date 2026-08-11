"""E-12 completeness, applied one layer later than the ingest gate.

`configs/physics_params.yaml` was fitted when only 2024 and 2025 had been ingested,
while `configs/ingest.yaml` has declared 2022-2026 the whole time. Nothing noticed: the
battery fitted whatever the database happened to hold, wrote the yaml, and recorded the
season scope nowhere. Restoring the A-09 snapshot and running `make fit` therefore does
not reproduce the shipped physics — it moves base pace at Bahrain by about 0.9 s/lap —
so the reproducibility pack does not round-trip.

This is the gate that would have caught it, and it sits in the same place in the same
file as the F-14 quality-report gate: called before anything writes, raising rather than
returning a flag, and saying what to do about it.
"""

import pytest

from senna.physics.fits.gate import IncompleteSeasonCoverageError, assert_season_coverage

DECLARED_SEASONS = [2022, 2023, 2024, 2025, 2026]  # configs/ingest.yaml `seasons`


def test_a_partial_ingest_refuses_to_write_params():
    ingested_seasons = [2024, 2025]  # the scope that actually produced the committed file

    with pytest.raises(IncompleteSeasonCoverageError) as excinfo:
        assert_season_coverage(DECLARED_SEASONS, ingested_seasons)

    # run.py writes physics_params.yaml after this call, so raising is the refusal
    message = str(excinfo.value)
    assert "2022" in message
    assert "2023" in message
    assert "2026" in message
    # and, like the F-14 gate beside it, the message points somewhere: the declared
    # list to correct, or the ingest to finish
    assert "ingest" in message


def test_full_coverage_passes_the_gate():
    # deliberately shuffled: seasons arrive from a `unique()` over the circuit index,
    # and the gate must be about which seasons are present, not what order they land in
    ingested_seasons = [2026, 2022, 2025, 2023, 2024]

    assert assert_season_coverage(DECLARED_SEASONS, ingested_seasons) is None
