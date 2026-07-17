import ast
from pathlib import Path

import pytest

from senna.physics.synth.frames import refuse_validation_rounds

CALIBRATION_ROUNDS = [1, 2, 3, 4, 5, 6]  # frozen split (E-14, configs/data_split.yaml)
SYNTH_DIR = Path(__file__).parents[3] / "senna" / "physics" / "synth"
HELDOUT_EXEMPT = {"validate.py", "heldout.py"}  # the only sanctioned readers of rounds 7+


def test_calibration_loaders_refuse_rounds_7_plus(make_lap_frame):
    # Spec-mandated split guard (E-14): the pure check every calibration loader runs
    calibration = make_lap_frame(
        [{"round": r, "session_id": f"2026-{r:02d}-R"} for r in (1, 3, 6)]
    )
    refuse_validation_rounds(calibration, CALIBRATION_ROUNDS)  # rounds 1-6 pass silently

    # the split governs 2026 only; a 2024 round 10 is history, not held-out data
    old_era = make_lap_frame([{"season": 2024, "round": 10, "session_id": "2024-10-R"}])
    refuse_validation_rounds(old_era, CALIBRATION_ROUNDS)

    held_out = make_lap_frame(
        [
            {"round": 7, "session_id": "2026-07-R"},
            {"round": 3},
            {"round": 9, "session_id": "2026-09-R"},
        ]
    )
    # the error names every offending round, so the caller knows what leaked
    with pytest.raises(ValueError, match=r"round.*7, 9"):
        refuse_validation_rounds(held_out, CALIBRATION_ROUNDS)


def test_no_calibration_module_imports_heldout():
    # E-14, third layer: no calibration module may even import the held-out
    # loaders; checked on the parsed AST, not a substring grep, so a comment
    # mentioning heldout.py stays legal
    modules = [path for path in SYNTH_DIR.glob("*.py") if path.name not in HELDOUT_EXEMPT]
    assert modules, "senna/physics/synth is missing — the boundary check has nothing to inspect"

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
                    f"{module.name} imports held-out data — only validate.py may (E-14)"
                )
