"""The committed run store (A-09). `make report` reads only what lands here, so the
Chapter 7 tables regenerate from the repository alone — models/ is gitignored, which
rules out the episode-grain store being the thing the report reproduces from.

Determinism is the whole contract: sorted keys, a fixed indent, no timestamps anywhere.
A rerun that changed nothing must produce identical bytes, or "deterministic given the
run store" is unverifiable. Provenance rides in an envelope beside every payload — which
model, which configs, which seeds, which commit — because a number nobody can trace back
to the run that produced it is not evidence.
"""

import json
import subprocess
from pathlib import Path

from senna import config


def repo_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=config.REPO_ROOT,
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() or "unknown"


def envelope(*, model_versions: dict, config_hash: str, seeds_fingerprint: str,
             scope: dict | None = None) -> dict:
    """Provenance for one stored metric. `scope` says how much of the bank produced it —
    without it a two-circuit smoke row and a full 480-race row are indistinguishable on
    disk, and the report would print the smoke number under the full run's claim."""
    return {
        "model_versions": dict(model_versions),
        "config_hash": config_hash,
        "seeds_fingerprint": seeds_fingerprint,
        "git_commit": repo_commit(),
        "scope": dict(scope or {}),
    }


def write_metric(store_dir, name: str, payload: dict, *, envelope: dict) -> Path:
    path = Path(store_dir) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"envelope": envelope, "payload": payload},
                      sort_keys=True, indent=2, ensure_ascii=False)
    path.write_text(body + "\n")
    return path


def read_metric(store_dir, name: str) -> dict:
    return json.loads((Path(store_dir) / f"{name}.json").read_text())
