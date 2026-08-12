"""Era threading for the explain pipeline (F15, F-24). senna/explain/run.py froze
_ERA = "2026", so running it against the era-matched 2024 triplet would distill the
2024 model on 2026 physics — explaining a policy against a world it never raced. The
pinned seams: one env builder that every distillation and card env goes through, and
the circuit narrowing that keeps a 2024 run off circuits with no native 2024 fits
(the same refusal require_native_era_fits already enforces for M2).

The file is not named test_era.py: tests/train/test_era.py exists, and without
__init__.py files pytest imports test modules by basename.
"""

from pathlib import Path

import pytest

from senna import config
from senna.eval.traces import EraFitError, require_native_era_fits
from senna.explain.run import era_circuits, explain_env
from senna.train.seeds import load_banks

CIRCUIT = "bahrain_grand_prix"  # a raced event with fitted params in both eras


def test_explain_era_threading():
    threaded = explain_env(CIRCUIT, era="2024", rival_band="train")
    assert threaded.era == "2024"
    # the 2024 field is 20 cars (physics_2024.yaml); 22 here means the era never
    # reached build_scenario and the surrogate would be distilled on 2026 physics
    assert threaded.scenario.grid_size == 20

    default = explain_env(CIRCUIT)
    assert default.era == "2026"  # the headline default, same as the CLI's --era
    assert default.scenario.grid_size == 22


def test_explain_narrows_to_native_era_fits():
    banks = load_banks()
    # the Stage C bank is wider than the era-matched fine-tune's circuit list, so the
    # narrowing has real work to do. Canada is the case in point: it rides the bank
    # (configs/seeds.yaml) and is not an era_finetune circuit, so a 2024 run must not
    # card it (F-24)
    assert "canadian_grand_prix" in banks.stage_c_validation

    narrowed = era_circuits(banks, "2024")
    assert "canadian_grand_prix" not in narrowed
    native = set(config.load("eval")["era_finetune"]["circuits"])
    assert narrowed == sorted(set(banks.stage_c_validation) & native)
    for circuit in narrowed:
        require_native_era_fits(circuit, "2024")  # the guard agrees, not just the list
    # the guard's refusal path runs against a fixture rather than a real circuit: the
    # F18 refit gave every circuit native 2024 fits, so no real slug reaches it any more
    gaps = Path(__file__).resolve().parents[1] / "eval" / "fixtures" / "era_fit_gaps"
    with pytest.raises(EraFitError):
        require_native_era_fits("no_2024_joint_grand_prix", "2024", configs_dir=gaps)

    # 2026 keeps the whole bank: the 2026 scenarios come from the transform chain,
    # not physics_params joint-pace rows, so the 2024 guard has nothing to say there
    assert era_circuits(banks, "2026") == sorted(banks.stage_c_validation)
