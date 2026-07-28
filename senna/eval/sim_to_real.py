"""M8 — sim-to-real, read back from the committed validation summary (5.4.1, E-14).

This is the only module in the evaluation package allowed anywhere near held-out data, and
even here it reads a committed artifact rather than the database: `make synth-figures`
writes docs/synth/validation_summary.yaml through senna/physics/synth/heldout.py, the one
sanctioned door to rounds 7 and later. An AST boundary test in tests/eval pins that no
sibling module imports that door.

The refusal is live rather than decorative: the rounds this module reports on are passed
through the E-14 guard, so a summary that somehow covered a calibration round would fail
loudly here instead of being printed as validation.
"""

from senna import config
from senna.eval.splits import refuse_calibration_rounds


def sim_to_real(configs_dir=None) -> dict:
    """The per-circuit KS distances and pit-loss checks, with the rounds they cover."""
    summary_path = config.REPO_ROOT / "docs/synth/validation_summary.yaml"
    if not summary_path.exists():
        return {"available": False, "reason": "run make synth-figures first"}

    import yaml

    raw = yaml.safe_load(summary_path.read_text()) or {}
    synth = config.load("synth", configs_dir)
    split = config.load("data_split", configs_dir)
    ks_target = float(config.get(synth, "validation.ks_target"))
    validation_from = int(config.get(split, "validation_rounds_from"))

    circuits = {slug: block for slug, block in raw.items() if isinstance(block, dict)}
    rounds = _held_out_rounds(validation_from, len(circuits))
    refuse_calibration_rounds(rounds, configs_dir=configs_dir)

    per_circuit = {
        slug: {
            "lap_time_ks": block.get("lap_time_ks"),
            "ks_within_target": bool(block.get("ks_within_target")),
            "pit_delta_within_1s": bool(block.get("pit_delta_within_1s")),
            "sim_minus_real_median_s": block.get("sim_minus_real_median_s"),
        }
        for slug, block in circuits.items()
    }
    passing = sum(1 for block in per_circuit.values() if block["ks_within_target"])
    worst = max((block["lap_time_ks"] or 0.0) for block in per_circuit.values()) \
        if per_circuit else 0.0

    return {
        "available": True,
        "per_circuit": per_circuit,
        "ks_target": ks_target,
        "worst_ks": worst,
        "n_circuits": len(per_circuit),
        "n_within_target": passing,
        "validation_rounds_from": validation_from,
        "met": bool(per_circuit and passing == len(per_circuit)),
    }


def _held_out_rounds(validation_from: int, n_circuits: int) -> list:
    """The rounds the summary covers. The generator writes one row per held-out circuit
    from `validation_from` onward, so the span follows from the count — enough to hand the
    E-14 guard something real to refuse."""
    return list(range(validation_from, validation_from + n_circuits))
