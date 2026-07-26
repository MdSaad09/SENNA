"""The frozen-split guard, applied to evaluation (E-14).

Rounds 1-6 of 2026 calibrated the synthetic generator. Scoring the agent against them and
calling the result validation would be grading the model on its own training data, and the
circularity would be invisible in the output — the numbers would simply look good. So the
refusal is mechanical and loud, mirroring senna/physics/synth/frames.py: the same rule, at
the other end of the pipeline.

The held-out rounds themselves are reachable from exactly one module in this package
(sim_to_real.py, which owns M8) and only through senna/physics/synth/heldout.py. An AST
import boundary in tests/eval keeps it that way.
"""

from senna import config


def calibration_rounds(configs_dir=None) -> list:
    return list(config.get(config.load("data_split", configs_dir), "calibration_rounds"))


def refuse_calibration_rounds(rounds, *, configs_dir=None) -> None:
    frozen = set(calibration_rounds(configs_dir))
    offending = sorted({int(number) for number in rounds} & frozen)
    if offending:
        named = ", ".join(str(number) for number in offending)
        raise ValueError(
            f"2026 round {named} calibrated the synthetic generator — evaluating on it "
            "is train-test contamination (E-14, configs/data_split.yaml). The held-out "
            "rounds start at "
            f"{config.get(config.load('data_split', configs_dir), 'validation_rounds_from')}"
        )
