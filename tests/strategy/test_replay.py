"""The replayed-real baseline (A-07): a recorded strategy's stops replayed against the
2026 physics. It runs balanced modes everywhere (a 2024 strategy carries no 2026 energy
decision), and when the mask blocks a recorded stop it defers a few laps then snaps to
the nearest legal compound, counting every deviation into EpisodeResult.snapped. The
offline extractor that compiles a real race into a plan is pure — pandas in, plan out,
no database.
"""

import pandas as pd
import pytest
import yaml

from senna import config
from senna.env import events
from senna.strategy.extract import compile_plan
from senna.strategy.plans import PitPlan
from senna.strategy.replay import RealStrategyReplay, load_real_plan
from senna.strategy.rollout import run_episode
from tests.strategy.conftest import CIRCUIT, SEED


def _stint_frame(stints):
    """One driver's laps as FastF1-shaped columns; pit_in_time_s is non-null only on the
    last lap of a stint that ended in a stop. `stints` is (laps, compound, ended_in_stop)."""
    rows = []
    lap = 1
    for stint_number, (n_laps, compound, ended_in_stop) in enumerate(stints, start=1):
        for offset in range(n_laps):
            is_last = offset == n_laps - 1
            rows.append(
                {
                    "lap_number": lap,
                    "stint": stint_number,
                    "compound": compound,
                    "pit_in_time_s": 4200.0 if (is_last and ended_in_stop) else None,
                }
            )
            lap += 1
    return pd.DataFrame(rows)


def test_a_recorded_real_strategy_replays_its_stops_at_the_recorded_laps(
    make_env, green_trace
):
    plan = load_real_plan(CIRCUIT)
    env = make_env(twin=green_trace)
    policy = RealStrategyReplay(plan, env.scenario, config.load("baselines")["replay"])
    result = run_episode(env, policy, seed=SEED)

    assert result.pit_laps == [lap for lap, _ in plan.stops]
    assert result.compounds == [compound for _, compound in plan.stops]
    assert result.snapped == 0


def test_an_illegal_recorded_compound_defers_then_snaps_and_is_counted(
    make_env, green_trace
):
    wet_from = 20
    # the env commits to a pit the lap before it is driven, so the mask for the lap-20 stop
    # reflects the previous lap's weather: wet the track from a lap earlier so the decision
    # for the recorded stop actually sees the rain
    green_trace.wetness[wet_from - 2 :] = 0.5  # slicks masked, only inters legal here
    green_trace.weather[wet_from - 2 :] = events.DAMP
    plan = PitPlan(stops=((wet_from, "SOFT"),))  # a slick call onto a wet track

    env = make_env(twin=green_trace)
    policy = RealStrategyReplay(plan, env.scenario, config.load("baselines")["replay"])
    result = run_episode(env, policy, seed=SEED)

    assert result.snapped >= 1
    assert "SOFT" not in result.compounds  # the illegal slick never actually ran
    assert result.compounds == ["INTERMEDIATE"]  # the only compound legal at wetness 0.5


def test_the_extractor_compiles_stints_into_a_plain_plan():
    frame = _stint_frame([(20, "MEDIUM", True), (20, "HARD", True), (17, "SOFT", False)])

    # identity lap map: the out-lap after each pit-in, compound taken from the next stint
    identity = compile_plan(frame, sim_total_laps=57, real_total_laps=57)
    assert identity.stops == ((21, "HARD"), (41, "SOFT"))

    # a shortened sim rounds each real out-lap: 21*40/57 -> 15, 41*40/57 -> 29
    shortened = compile_plan(frame, sim_total_laps=40, real_total_laps=57)
    assert shortened.stops == ((15, "HARD"), (29, "SOFT"))


def _entry(season, circuit, driver, stops):
    """One re-keyed real_strategies.yaml entry (F15): season, circuit and driver are
    explicit fields, so the top-level key is derivable and never load-bearing alone."""
    return {
        "season": season, "circuit": circuit, "driver": driver,
        "source": f"FastF1 {season} {circuit}, {driver} — test fixture",
        "real_total_laps": 52, "sim_total_laps": 52,
        "stops": [list(stop) for stop in stops],
    }


def _strategies_dir(tmp_path, entries):
    (tmp_path / "real_strategies.yaml").write_text(yaml.safe_dump(entries, sort_keys=False))
    return tmp_path


def test_a_bare_circuit_with_one_recorded_race_needs_no_selector(tmp_path):
    configs = _strategies_dir(tmp_path, {
        "2024_bahrain_grand_prix_VER": _entry(
            2024, "bahrain_grand_prix", "VER", ((18, "HARD"), (38, "SOFT"))),
    })

    plan = load_real_plan("bahrain_grand_prix", configs_dir=configs)
    assert plan.stops == ((18, "HARD"), (38, "SOFT"))


def test_two_recorded_races_on_one_circuit_are_refused_naming_both(tmp_path):
    # M2 carries two British GPs by design (2024 HAM, 2023 NOR) — a bare-circuit
    # lookup has no honest answer there, and the refusal must hand over the keys
    configs = _strategies_dir(tmp_path, {
        "2024_british_grand_prix_HAM": _entry(
            2024, "british_grand_prix", "HAM", ((28, "HARD"),)),
        "2023_british_grand_prix_NOR": _entry(
            2023, "british_grand_prix", "NOR", ((34, "SOFT"),)),
    })

    with pytest.raises(LookupError) as refused:
        load_real_plan("british_grand_prix", configs_dir=configs)
    assert "2024_british_grand_prix_HAM" in str(refused.value)
    assert "2023_british_grand_prix_NOR" in str(refused.value)


def test_season_and_driver_select_between_two_recorded_races(tmp_path):
    configs = _strategies_dir(tmp_path, {
        "2024_british_grand_prix_HAM": _entry(
            2024, "british_grand_prix", "HAM", ((28, "HARD"),)),
        "2023_british_grand_prix_NOR": _entry(
            2023, "british_grand_prix", "NOR", ((34, "SOFT"),)),
    })

    plan = load_real_plan("british_grand_prix", season=2023, driver="NOR",
                          configs_dir=configs)
    assert plan.stops == ((34, "SOFT"),)


def test_a_replayed_strategy_runs_balanced_modes_everywhere(make_env, green_trace):
    plan = PitPlan(stops=((28, "HARD"),))
    env = make_env(twin=green_trace)
    policy = RealStrategyReplay(plan, env.scenario, config.load("baselines")["replay"])
    result = run_episode(env, policy, seed=SEED)

    assert all(int(action[1]) == 1 for action in result.actions)  # 1 == balanced
