import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# docs/ stays out of scope: the spec itself names the dead service (R-04)
CODE_DIRS = ("senna/", "api/", "worker/", "scripts/", "configs/", "tests/", "notebooks/")


def test_no_code_path_can_reach_the_dead_results_service():
    # R-04 / F-10: the service died in early 2025; Jolpica via fastf1>=3.7 replaced it.
    # The needle is assembled at runtime, case-insensitively, and stays out of this
    # file's own name and content so the guard passes its own scan.
    needle = ("erg" + "ast").casefold()
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    offenders = [
        path for path in tracked if path.startswith(CODE_DIRS) and needle in path.casefold()
    ]
    for path in tracked:
        if not path.startswith(CODE_DIRS):
            continue
        if needle in (REPO_ROOT / path).read_text(errors="ignore").casefold():
            offenders.append(path)
    assert offenders == []
