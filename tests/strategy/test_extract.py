"""plan_from_rows — the pure heart of F13's real-strategy extraction. The
counterfactual route calls it straight off a driver's ingested laps, and compile_plan
becomes a thin pandas adapter over it, so rows travel as bare tuples in the extract
query's column order: (lap_number, stint, compound, pit_in_time_s). No pandas and no
database anywhere near it — the worker never touches either (F13 plan decision 3).
"""

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from senna import config
from senna.env.scenario import COMPOUNDS
from senna.strategy.extract import plan_from_rows


def _stint_rows(stints):
    """One driver's laps as extract-query tuples; pit_in_time_s is non-null only on the
    last lap of a stint that ended in a stop. `stints` is (laps, compound, ended_in_stop)."""
    rows = []
    lap = 1
    for stint_number, (n_laps, compound, ended_in_stop) in enumerate(stints, start=1):
        for offset in range(n_laps):
            is_last = offset == n_laps - 1
            rows.append(
                (lap, stint_number, compound, 4200.0 if (is_last and ended_in_stop) else None)
            )
            lap += 1
    return rows


def test_a_three_stint_race_stops_at_each_next_stints_out_lap_on_its_compound():
    rows = _stint_rows([(20, "MEDIUM", True), (20, "HARD", True), (17, "SOFT", False)])
    plan = plan_from_rows(rows, sim_total_laps=57, real_total_laps=57)
    assert plan.stops == ((21, "HARD"), (41, "SOFT"))


def test_the_final_stint_yields_no_stop_even_when_it_ends_in_the_pits():
    # a driver who retired into the pits: the final stint's pit-in is the race ending,
    # never a tyre change
    rows = _stint_rows([(30, "MEDIUM", True), (27, "HARD", True)])
    plan = plan_from_rows(rows, sim_total_laps=57, real_total_laps=57)
    assert plan.stops == ((31, "HARD"),)


def test_stint_less_rows_yield_the_empty_plan():
    # FastF1 leaves Stint NaN on some historic loads and ingest stores that as null —
    # there is no strategy to read, and inventing one would fabricate the comparison
    rows = [(lap, None, "MEDIUM", None) for lap in range(1, 11)]
    assert plan_from_rows(rows, sim_total_laps=57, real_total_laps=57).stops == ()


def test_matching_sim_and_real_distances_are_an_identity_lap_map():
    rows = _stint_rows([(10, "MEDIUM", True), (34, "HARD", False)])
    plan = plan_from_rows(rows, sim_total_laps=44, real_total_laps=44)
    assert plan.stops == ((11, "HARD"),)


def test_extract_writes_a_driver_entry(tmp_path):
    """The F15 --driver/--write pass: extraction merges into real_strategies.yaml
    instead of printing and walking away (the docstring has claimed the write since
    F06). The merge is tested at its pure seam — extract dict plus existing yaml text
    in, yaml text out — so no live database is anywhere near it."""
    # the writer seam lands with F15; importing it inside keeps the pure
    # plan_from_rows suite collectable until it does (the strategy conftest precedent)
    from senna.strategy.extract import merge_strategy
    from senna.strategy.replay import load_real_plan

    existing = yaml.safe_dump({
        "2024_bahrain_grand_prix_VER": {
            "season": 2024, "circuit": "bahrain_grand_prix", "driver": "VER",
            "source": "FastF1 2024 Bahrain Grand Prix, VER — senna.strategy.extract",
            "real_total_laps": 57, "sim_total_laps": 57,
            "stops": [[18, "HARD"], [38, "SOFT"]],
        },
    }, sort_keys=False)
    entry = {
        "season": 2024, "circuit": "british_grand_prix", "driver": "HAM",
        "source": "FastF1 2024 British Grand Prix, HAM — senna.strategy.extract",
        "real_total_laps": 52, "sim_total_laps": 52,
        "stops": [[28, "HARD"], [40, "SOFT"]],
    }

    merged = merge_strategy(existing, entry)
    (tmp_path / "real_strategies.yaml").write_text(merged)

    plan = load_real_plan("british_grand_prix", configs_dir=tmp_path)
    assert plan.stops == ((28, "HARD"), (40, "SOFT"))
    # what was already recorded rides through the merge untouched
    bahrain = load_real_plan("bahrain_grand_prix", configs_dir=tmp_path)
    assert bahrain.stops == ((18, "HARD"), (38, "SOFT"))

    written = yaml.safe_load(merged)["2024_british_grand_prix_HAM"]
    assert (written["season"], written["circuit"], written["driver"]) == (
        2024, "british_grand_prix", "HAM")


def test_real_strategies_covers_all_m2_races():
    """The committed yaml is the human-readable record of every M2 replay (A-07);
    a missing entry means the extract --write pass skipped one of the ten frozen
    counterfactual races."""
    races = config.load("eval")["m2"]["races"]
    recorded = config.load("real_strategies")

    assert len(races) == 10  # the frozen set (eval.yaml m2.races, 26 Jul 2026)
    for race in races:
        key = f"{race['season']}_{race['circuit']}_{race['driver']}"
        assert key in recorded, f"real_strategies.yaml is missing {key}"
        entry = recorded[key]
        assert entry["season"] == race["season"]
        assert entry["circuit"] == race["circuit"]
        assert entry["driver"] == race["driver"]
        assert entry["stops"], f"{key} records no stops — nothing to replay"


@pytest.mark.property
@given(
    layout=st.lists(
        st.tuples(
            st.integers(min_value=3, max_value=30),  # stint length in laps
            st.sampled_from(COMPOUNDS),
            st.booleans(),                           # ended in a pit stop
        ),
        min_size=1,
        max_size=5,
    ),
    sim_total_laps=st.integers(min_value=30, max_value=80),  # the 5.9.2 race-length range
)
@settings(max_examples=200, deadline=None)
def test_random_stint_layouts_always_map_to_a_legal_ordered_stop_list(layout, sim_total_laps):
    rows = _stint_rows(layout)
    real_total_laps = sum(n_laps for n_laps, _, _ in layout)
    plan = plan_from_rows(rows, sim_total_laps=sim_total_laps, real_total_laps=real_total_laps)

    laps = [lap for lap, _ in plan.stops]
    # every pit-ended stint before the last maps to exactly one stop, however the
    # rescale rounds — dropping a collided stop would understate the real strategy
    assert len(laps) == sum(ended for _, _, ended in layout[:-1])
    assert all(earlier < later for earlier, later in zip(laps, laps[1:], strict=False))
    assert all(1 <= lap <= sim_total_laps for lap in laps)
