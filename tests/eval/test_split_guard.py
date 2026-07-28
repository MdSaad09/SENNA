"""The frozen-split guard, extended to the evaluation package (E-14). Rounds 1-6 of 2026
calibrated the synthetic generator; anything that scores the agent against them is
grading the model on its own training data. Same three layers as senna/physics/synth:
a runtime refusal that names the offending rounds, and an AST import boundary so only
the sanctioned sim-to-real module can reach the held-out loaders.
"""

import ast
from pathlib import Path

import pytest

from senna.eval.splits import refuse_calibration_rounds

CALIBRATION_ROUNDS = [1, 2, 3, 4, 5, 6]  # frozen split (E-14, configs/data_split.yaml)
EVAL_DIR = Path(__file__).parents[2] / "senna" / "eval"
HELDOUT_EXEMPT = {"sim_to_real.py"}  # the only sanctioned reader of rounds 7+


def test_split_guard_2026_calibration_rounds_fail_loudly():
    refuse_calibration_rounds([7, 8, 9, 10])  # the held-out rounds are what M8 validates on
    refuse_calibration_rounds([12])
    refuse_calibration_rounds([])

    # the error names every offending round, so the caller knows what leaked
    with pytest.raises(ValueError, match=r"round.*1, 4"):
        refuse_calibration_rounds([4, 9, 1])

    for calibration_round in CALIBRATION_ROUNDS:
        with pytest.raises(ValueError, match=str(calibration_round)):
            refuse_calibration_rounds([calibration_round, 8])


def test_no_eval_module_imports_heldout_except_the_sanctioned_one():
    # checked on the parsed AST rather than a substring grep, so a comment naming
    # heldout.py stays legal
    modules = [path for path in EVAL_DIR.glob("*.py") if path.name not in HELDOUT_EXEMPT]
    assert modules, "senna/eval is missing — the boundary check has nothing to inspect"

    for module in modules:
        for node in ast.walk(ast.parse(module.read_text())):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # `from . import heldout` carries the name on the alias, not the module
                imported = [node.module or ""] + [alias.name for alias in node.names]
            for name in imported:
                assert "heldout" not in name.split("."), (
                    f"{module.name} imports held-out data — only sim_to_real.py may (E-14)"
                )
