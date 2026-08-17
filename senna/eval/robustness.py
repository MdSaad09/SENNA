"""Strategy robustness: does the agent respond to the physics, or to this physics?

An agent that memorised one parameter set would make the same call whatever you did to
the world. An agent that learned the structure of the problem should move its stop in
the direction a strategist would predict when you change what a stop is worth. That is
what this measures, and it is a decision-level question rather than an outcome-level
one: the existing sensitivity studies ask what happens to the agent's *results* when a
constant moves, and this asks what happens to its *choices*.

Two knobs, each up and down, on the three archetypes. Both are single numbers in
configs/physics_params.yaml, so an arm is a copy of the config tree with one field
scaled and nothing else touched — a diff of an overlay is the complete statement of what
changed, which is the same discipline the harvest and energy-coefficient studies use.

Direction is the finding, not magnitude. A stop that moves two laps the right way is
evidence the agent is reading the trade; a stop that does not move at all is evidence it
is not, whatever the size of the perturbation.

Not every knob supports that reading, and the difference is recorded rather than
smoothed over. A knob is `controlled` when the perturbation changes the physics and
leaves the race otherwise intact, so a moved stop can only be the policy responding.
A knob is `confounded` when it changes the event distribution itself: raise the
safety-car rate and a different safety car happens on a different lap, so the stop
moves whether or not the policy noticed anything. Confounded arms are still worth
running — a policy that cannot respond to a changed world is worth knowing about — but
their movement is not evidence of a decision, and the payload says so per arm.
"""

import argparse
import logging
import shutil
import tempfile
from pathlib import Path

import yaml

from senna import config
from senna.eval import store
from senna.eval.archetypes import ARCHETYPES

log = logging.getLogger(__name__)

# stylised — a perturbation big enough to matter and small enough to stay plausible.
# 10% of a fitted degradation coefficient is well inside the spread between circuits;
# two seconds is about 8% of a typical 24 s pit loss and about the difference between a
# clean stop and a fumbled one.
# every config the arms read; the overlay changes one field inside physics_params
ROBUSTNESS_CONFIG_FILES = ["physics_params", "circuits", "eval", "env"]

KNOBS = {
    # controlled: the physics moves, the race does not
    "tyre_degradation": {
        "delta": 0.10, "unit": "relative", "kind": "controlled", "earlier_when": "up",
        "rationale": "harder wear should pull the stop earlier",
    },
    "pit_loss": {
        "delta": 2.0, "unit": "seconds", "kind": "controlled", "earlier_when": "down",
        "rationale": "an expensive stop should be delayed",
    },
    "energy_coefficients": {
        # what a megajoule is worth: conserve cost, attack gain, derate penalty
        "delta": 0.20, "unit": "relative", "kind": "controlled", "earlier_when": None,
        "rationale": "no directional prediction — this asks whether pit timing couples "
                     "to the energy model at all, and the expected answer is that it "
                     "should not move much",
    },
    # confounded: the event distribution itself moves, so the race is a different race
    "safety_car_rate": {
        "delta": 0.50, "unit": "relative", "kind": "confounded", "earlier_when": None,
        "rationale": "more neutralisations means more cheap stops, but it also means a "
                     "different race; movement here is not by itself a decision",
    },
    "rain_probability": {
        "delta": 0.50, "unit": "relative", "kind": "confounded", "earlier_when": None,
        "rationale": "the agent observes the weather it is in, never a forecast, so it "
                     "cannot anticipate this — only react once the track is wet",
    },
}


def _scale_degradation(params: dict, circuits: list[str], factor: float) -> None:
    for slug in circuits:
        for era_block in (params["circuits"][slug].get("degradation") or {}).values():
            for fit in (era_block or {}).values():
                fit["a"] = float(fit["a"]) * factor


def _shift_pit_loss(params: dict, circuits: list[str], seconds: float) -> None:
    for slug in circuits:
        block = params["circuits"][slug].get("pit_loss") or {}
        if "mean_s" in block:
            # a pit stop cannot cost negative time, however hard the arm pushes
            block["mean_s"] = max(float(block["mean_s"]) + seconds, 1.0)


# the energy-mode block: what a megajoule buys and what running dry costs
ENERGY_FIELDS = ("conserve_pace_cost_s_per_mj", "attack_pace_gain_s",
                 "derate_penalty_s_per_mj")


def _scale_energy(physics: dict, factor: float) -> None:
    for field in ENERGY_FIELDS:
        if field in physics.get("fitted", {}):
            physics["fitted"][field] = float(physics["fitted"][field]) * factor


def _scale_safety_car(params: dict, circuits: list[str], factor: float) -> None:
    """Both neutralisation kinds together: raising one and not the other would change
    which kind of neutralisation happens as well as how often."""
    for slug in circuits:
        for kind in ("sc", "vsc"):
            block = (params["circuits"][slug].get("hazards") or {}).get(kind) or {}
            for field in ("lambda_per_lap", "p_per_race"):
                if field in block:
                    # a probability cannot exceed one however hard the arm pushes
                    block[field] = min(float(block[field]) * factor, 1.0)


def _scale_rain(env_cfg: dict, factor: float) -> None:
    """Scale the dry->damp transition and renormalise the row. The Markov rows must sum
    to one, so the probability taken from staying dry is what goes into becoming damp."""
    rows = env_cfg["weather"]["markov"]
    dry, damp, wet = (float(v) for v in rows["dry"])
    damp = min(damp * factor, 1.0)
    rows["dry"] = [max(1.0 - damp - wet, 0.0), damp, wet]


def build_overlay(*, base_configs_dir, dest: Path, knob: str, direction: str,
                  circuits: list[str]) -> Path:
    """One config tree with one knob moved and nothing else."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(Path(base_configs_dir), dest)

    spec = KNOBS[knob]
    sign = 1.0 if direction == "up" else -1.0
    factor = 1.0 + sign * spec["delta"]

    if knob in ("tyre_degradation", "pit_loss", "safety_car_rate"):
        path = dest / "physics_params.yaml"
        params = yaml.safe_load(path.read_text())
        if knob == "tyre_degradation":
            _scale_degradation(params, circuits, factor)
        elif knob == "pit_loss":
            _shift_pit_loss(params, circuits, sign * spec["delta"])
        else:
            _scale_safety_car(params, circuits, factor)
        path.write_text(yaml.safe_dump(params, sort_keys=False))
    elif knob == "energy_coefficients":
        path = dest / "physics_2026.yaml"
        physics = yaml.safe_load(path.read_text())
        _scale_energy(physics, factor)
        path.write_text(yaml.safe_dump(physics, sort_keys=False))
    else:
        path = dest / "env.yaml"
        env_cfg = yaml.safe_load(path.read_text())
        _scale_rain(env_cfg, factor)
        path.write_text(yaml.safe_dump(env_cfg, sort_keys=False))

    return dest


def expected_direction(knob: str, direction: str) -> str | None:
    """What a strategist would predict the first stop does under this arm, or None where
    there is no defensible prediction to make. An arm with no prediction is not a failed
    arm: it measures whether the agent couples to that input at all."""
    earlier_when = KNOBS[knob]["earlier_when"]
    if earlier_when is None:
        return None
    return "earlier" if direction == earlier_when else "later"


def compare(baseline: dict, arm: dict) -> dict:
    """Per circuit and seed: which way the first stop moved, against the prediction."""
    moved = []
    for key, base_lap in baseline.items():
        arm_lap = arm.get(key)
        if arm_lap is None or base_lap is None:
            continue
        moved.append({"circuit": key[0], "seed": key[1],
                      "baseline_lap": base_lap, "arm_lap": arm_lap,
                      "shift": arm_lap - base_lap})
    return {
        "n": len(moved),
        "mean_shift_laps": (sum(m["shift"] for m in moved) / len(moved)) if moved else None,
        "moved_earlier": sum(m["shift"] < 0 for m in moved),
        "moved_later": sum(m["shift"] > 0 for m in moved),
        "unchanged": sum(m["shift"] == 0 for m in moved),
        "per_race": moved,
    }


def agreement(comparison: dict, predicted: str | None) -> float | None:
    """The share of races that moved the predicted way, of those that moved at all."""
    if predicted is None:
        return None
    moved = comparison["moved_earlier"] + comparison["moved_later"]
    if not moved:
        return None
    hit = comparison["moved_earlier"] if predicted == "earlier" else comparison["moved_later"]
    return hit / moved


def first_stops(results_by_circuit: dict) -> dict:
    """(circuit, seed) -> the lap of the agent's first stop, or None if it never boxed."""
    out = {}
    for circuit, (seeds, results) in results_by_circuit.items():
        for seed, result in zip(seeds, results, strict=True):
            stops = list(result.pit_laps or [])
            out[(circuit, int(seed))] = int(stops[0]) if stops else None
    return out


def _roll(policy, *, circuits, banks, seeds: int, configs_dir) -> dict:
    """The same (circuit, seed) races on whichever physics `configs_dir` describes."""
    from senna.eval import record

    out = {}
    for circuit in circuits:
        chosen = list(banks[circuit])[:seeds]
        out[circuit] = (chosen, record.roll_live_batch(
            policy, circuit=circuit, seeds=chosen, configs_dir=configs_dir))
    return out


# stylised — three slots spanning the grid: a front-row start, the midfield default the
# demo link uses, and a start behind most of the field. Enough to show whether strategy
# depends on where the race begins, without pretending twenty-two arms would say more.
GRID_SLOTS = (2, 8, 16)


def grid_sweep(policy, *, circuits, banks, seeds: int, configs_dir) -> dict:
    """Unlike the knobs, this changes the scenario rather than the world model: the
    physics is identical and the agent starts somewhere else. Grid position is visible
    to the policy — `position_frac` and `places_gained_frac` are both in the observation
    — so an agent whose stop does not move with it is not being starved of the input."""
    from senna.env import F1RaceEnv
    from senna.strategy.rollout import run_episode

    out = {}
    for slot in GRID_SLOTS:
        laps: list[int] = []
        for circuit in circuits:
            env = F1RaceEnv(circuit, "2026", rival_band="test", configs_dir=configs_dir)
            for seed in list(banks[circuit])[:seeds]:
                result = run_episode(env, policy, seed=int(seed),
                                     options={"grid_position": slot})
                stops = list(result.pit_laps or [])
                if stops:
                    laps.append(int(stops[0]))
        out[f"P{slot}"] = {
            "n": len(laps),
            "mean_first_stop_lap": (sum(laps) / len(laps)) if laps else None,
        }
    return out


def run(*, seeds: int, circuits: list[str] | None = None, configs_dir=None,
        models_dir=None) -> dict:
    """Race the frozen agent on the baseline physics and on each arm. Local only: needs
    models/headline.

    The seeds are the published test bank's, not new ones — the same races the reported
    metrics came from, so a shifted stop is the perturbation talking and not a different
    draw."""
    from senna.eval import record
    from senna.eval.run import load_frozen_policy

    circuits = circuits or list(ARCHETYPES)
    base_dir = Path(configs_dir) if configs_dir else config.REPO_ROOT / "configs"
    models = Path(models_dir) if models_dir else config.REPO_ROOT / "models"
    policy, _, _, manifest = load_frozen_policy(models / "headline")
    banks = record.test_bank(base_dir)

    log.info("baseline: %d circuits x %d seeds", len(circuits), seeds)
    baseline = first_stops(_roll(policy, circuits=circuits, banks=banks, seeds=seeds,
                                 configs_dir=base_dir))

    arms: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for knob in KNOBS:
            for direction in ("up", "down"):
                label = f"{knob}_{direction}"
                overlay = build_overlay(base_configs_dir=base_dir,
                                        dest=Path(scratch) / label, knob=knob,
                                        direction=direction, circuits=circuits)
                log.info("arm %s", label)
                rolled = _roll(policy, circuits=circuits, banks=banks, seeds=seeds,
                               configs_dir=overlay)
                predicted = expected_direction(knob, direction)
                comparison = compare(baseline, first_stops(rolled))
                arms[label] = {
                    "knob": knob, "direction": direction,
                    "perturbation": KNOBS[knob]["delta"], "unit": KNOBS[knob]["unit"],
                    "kind": KNOBS[knob]["kind"], "rationale": KNOBS[knob]["rationale"],
                    "predicted": predicted,
                    "direction_agreement": agreement(comparison, predicted),
                    **comparison,
                }

    log.info("grid sweep %s", list(GRID_SLOTS))
    grid = grid_sweep(policy, circuits=circuits, banks=banks, seeds=seeds,
                      configs_dir=base_dir)

    return {"model_version": manifest["model_version"], "seeds": seeds,
            "circuits": circuits, "arms": arms, "grid_sweep": grid}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--circuits", default=None,
                        help="comma-separated; defaults to the three archetypes")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    circuits = args.circuits.split(",") if args.circuits else None
    payload = run(seeds=args.seeds, circuits=circuits)

    # this study mutates physics_params on purpose, so it fingerprints its own overlay
    # inputs rather than copying the training-time manifest hash — the same convention
    # the harvest and energy-coefficient studies use (tests/eval/test_freeze.py). The
    # seeds are the frozen bank's, so that fingerprint is the real one.
    envelope = store.envelope(
        model_versions={"headline": payload["model_version"]},
        config_hash=config.fingerprint(ROBUSTNESS_CONFIG_FILES),
        seeds_fingerprint=config.fingerprint(["seeds"]),
        scope={"circuits": len(payload["circuits"]), "seeds_per_circuit": args.seeds,
               "arms": sorted(payload["arms"])},
    )
    out = Path(args.out) if args.out else config.REPO_ROOT / "docs" / "results" / "F14" / "store"
    log.info("wrote %s", store.write_metric(out, "robustness", payload, envelope=envelope))


if __name__ == "__main__":
    main()
