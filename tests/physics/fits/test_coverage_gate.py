"""E-12 completeness, applied at the two layers below the ingest gate.

Be exact about which gate catches what, because the obvious reading of the F18 defect is
wrong. `configs/physics_params.yaml` was NOT written from a store missing seasons: its own
watermark read "seasons 2022-2026, round 6", and its hazards blocks counted races from
every season including the French GP, which only ran in 2022. `assert_season_coverage`
would have passed that run without a word.

What went missing was one layer down. 2022 and 2023 laps reached hazards, pit loss and
energy, and reached none of the joint pace fits, so Bahrain's era-2024 base pace came from
1958 laps of an available 3705 — about 0.9 s/lap — and nothing in the file recorded the
narrower scope. `assert_pace_season_coverage` is the gate for that, and
`test_refit_reproduces_the_committed_params` is the one that actually failed on main.

Both are tested here twice over: the pure function, and the call site in `run_battery`,
because a gate the writer does not consult is not a gate.
"""

import argparse
import asyncio
from types import SimpleNamespace

import pandas as pd
import pytest

from senna import config
from senna.physics.fits import run as fits_run
from senna.physics.fits.gate import (
    IncompletePaceCoverageError,
    IncompleteSeasonCoverageError,
    assert_pace_season_coverage,
    assert_season_coverage,
)
from senna.physics.fits.params_writer import IncompleteParamsError

DECLARED_SEASONS = [2022, 2023, 2024, 2025, 2026]  # configs/ingest.yaml `seasons`

PARTIAL_INDEX = pd.DataFrame(
    # the scope that actually produced the committed file: 2024 and 2025 only
    [{"season": s, "round": 1, "event_name": "Bahrain Grand Prix", "session_id": f"{s}-01-R",
      "session_name": "Race", "is_dry": True, "era": "2024", "slug": "bahrain_grand_prix"}
     for s in (2024, 2025)]
)


GOOD_PARAMS = {"monza": {"pit_loss": {"mean_s": (21.4, "fitted: nb.ipynb")}}}


def _wire_battery_out(monkeypatch, index, *, params=None, pace_seasons=None):
    """Everything between the gates and the write, stubbed. The battery itself needs
    Postgres and minutes of FastF1; what is under test is whether run_battery consults
    each gate at all, so the fake is one that would otherwise happily write.

    `pace_seasons` defaults to whatever the index holds, which is the passing case. Pass
    a narrower dict to stand in for a season that arrived but reached no regression.
    """
    async def fake_index(_conn, _rounds):
        return index

    class _Conn:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False

    class _Engine:
        def connect(self): return _Conn()
        async def dispose(self): return None

    if pace_seasons is None:
        pace_seasons = {era: set(index[index["era"] == era]["season"].astype(int))
                        for era in index["era"].unique()}

    monkeypatch.setattr(fits_run.frames, "circuit_index", fake_index)
    monkeypatch.setattr(fits_run, "engine_for", lambda _url: _Engine())
    monkeypatch.setattr(fits_run, "database_url", lambda: "postgresql+asyncpg://x/y_test")
    monkeypatch.setattr(fits_run, "assert_quality_reports", lambda *a, **k: None)
    monkeypatch.setattr(
        fits_run, "_Battery",
        lambda *a, **k: SimpleNamespace(
            run=lambda _m: asyncio.sleep(0),
            params=lambda: GOOD_PARAMS if params is None else params,
            data_through=lambda: "seasons 2022-2026, round 6",
            pace_seasons=pace_seasons,
            # F17 writes a second file from these; empty is the honest stub here,
            # because this module is about the write gates, not the driver fits
            joint={},
            deg_style={},
        ),
    )


def _out(tmp_path, *, only=None, circuit=None):
    """The battery's CLI arguments, pointed at a scratch directory.

    Both out-paths are per-file since F17: the battery writes physics_params.yaml and
    drivers.yaml, and a test that redirected only one would rewrite the committed other.
    """
    return argparse.Namespace(
        only=only, circuit=circuit,
        params_out=tmp_path / "physics_params.yaml",
        drivers_out=tmp_path / "drivers.yaml",
    )


def _full_index():
    return pd.concat([PARTIAL_INDEX.assign(season=s) for s in DECLARED_SEASONS],
                     ignore_index=True)


def test_a_clean_full_run_writes_the_params_file(monkeypatch, tmp_path):
    """The positive control. Every other test here asserts a file is absent, so without
    this one a writer that silently stopped writing would pass the whole module."""
    _wire_battery_out(monkeypatch, _full_index())
    args = _out(tmp_path, only=None, circuit=None)

    asyncio.run(fits_run.run_battery(args))

    assert args.params_out.exists()
    text = args.params_out.read_text()
    assert text.startswith("# SENNA")
    assert "monza" in text and "21.4" in text
    # since F17 a full run writes a pair, and the two gates run before either file lands —
    # a physics file on disk beside a refused driver table is a worse state than neither
    assert args.drivers_out.exists()
    assert args.drivers_out.read_text().startswith("# SENNA")


def test_a_season_reaching_no_pace_fit_refuses_to_write(monkeypatch, tmp_path):
    # the F18 defect's real shape, driven through the writer: every declared season is
    # in the index, only two of them reached a regression
    _wire_battery_out(monkeypatch, _full_index(),
                      pace_seasons={"2024": {2024, 2025}})
    args = _out(tmp_path, only=None, circuit=None)

    with pytest.raises(IncompletePaceCoverageError):
        asyncio.run(fits_run.run_battery(args))

    assert not args.params_out.exists()


def test_an_untagged_constant_refuses_to_write(monkeypatch, tmp_path):
    # validate_origins is the third write gate and had no wiring test either
    _wire_battery_out(monkeypatch, _full_index(),
                      params={"monza": {"pit_loss": {"mean_s": (21.4, "")}}})
    args = _out(tmp_path, only=None, circuit=None)

    with pytest.raises(IncompleteParamsError) as excinfo:
        asyncio.run(fits_run.run_battery(args))

    assert "monza.pit_loss.mean_s" in str(excinfo.value)
    assert not args.params_out.exists()


def test_a_partial_ingest_refuses_to_write_params(monkeypatch, tmp_path):
    _wire_battery_out(monkeypatch, PARTIAL_INDEX)
    args = _out(tmp_path, only=None, circuit=None)

    with pytest.raises(IncompleteSeasonCoverageError):
        asyncio.run(fits_run.run_battery(args))

    # the refusal is the whole point: a partial ingest must leave no artifact behind
    assert not args.params_out.exists()


def test_a_narrowed_run_is_not_tripped_by_its_own_smaller_index(monkeypatch, tmp_path):
    _wire_battery_out(monkeypatch, PARTIAL_INDEX)
    args = _out(tmp_path, only="joint_pace", circuit=None)

    asyncio.run(fits_run.run_battery(args))

    # a narrowed run never writes, so the coverage question does not arise for it
    assert not args.params_out.exists()


def test_a_non_finite_fit_refuses_to_write_params(monkeypatch, tmp_path):
    _wire_battery_out(
        monkeypatch, _full_index(),
        params={"monza": {"pit_loss": {"mean_s": (float("nan"), "fitted: nb")}}},
    )
    args = _out(tmp_path, only=None, circuit=None)

    with pytest.raises(IncompleteParamsError):
        asyncio.run(fits_run.run_battery(args))

    # without this the emitter renders the bare literal `nan` and F05 loads it as a float
    assert not args.params_out.exists()


def test_a_season_that_reaches_no_pace_fit_refuses_to_write_params():
    # the defect's real shape: every season in the store, only two of them in the
    # regression. 2026 is its own era and is unaffected, which is why the check is
    # per era rather than over one flat season list.
    with pytest.raises(IncompletePaceCoverageError) as excinfo:
        assert_pace_season_coverage(
            reached={"2024": {2024, 2025}, "2026": {2026}},
            index_seasons={"2024": {2022, 2023, 2024, 2025}, "2026": {2026}},
        )

    message = str(excinfo.value)
    assert "2022" in message and "2023" in message
    # an operator reading this needs the next move, not just the fact
    assert "dry" in message or "era" in message


def test_one_circuit_short_of_slick_laps_is_not_a_coverage_failure():
    # a circuit skipped for want of dry slick laps is ordinary; the gate only fires
    # when a whole season contributed to nothing, or it would cry wolf every wet year
    assert assert_pace_season_coverage(
        reached={"2024": {2022, 2023, 2024, 2025}},
        index_seasons={"2024": {2022, 2023, 2024, 2025}},
    ) is None


def test_the_gate_rejects_a_partial_season_list():
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


def test_both_write_gates_are_declared_with_provenance():
    # the interpretability contract: a gate that lives only in code is a constant nobody
    # can find. Both are `operational` -- engineering defaults, not fitted or sourced
    # numbers -- and both are in the fingerprint every model manifest records, so a
    # change here is a change to what the trained artifacts were produced under.
    lines = (config.REPO_ROOT / "configs" / "fits.yaml").read_text().splitlines()
    gates = config.get(config.load("fits"), "gates")

    assert gates["require_full_season_coverage"] is True
    assert gates["require_finite_params"] is True
    for name in ("require_full_season_coverage", "require_finite_params"):
        start = next(i for i, row in enumerate(lines) if row.strip().startswith(name))
        # the tag may sit anywhere in the key's comment block, which wraps over several
        # lines; a same-line-only check breaks the moment someone rewraps a comment
        block = [lines[start]]
        for row in lines[start + 1:]:
            if not row.strip().startswith("#"):
                break
            block.append(row)
        assert "operational" in " ".join(block), f"{name} has no provenance tag"


def test_full_coverage_passes_the_gate():
    # deliberately shuffled: seasons arrive from a `unique()` over the circuit index,
    # and the gate must be about which seasons are present, not what order they land in
    ingested_seasons = [2026, 2022, 2025, 2023, 2024]

    assert assert_season_coverage(DECLARED_SEASONS, ingested_seasons) is None
