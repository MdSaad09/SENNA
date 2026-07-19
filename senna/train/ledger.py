"""models/runs.json — one row per training run, the machine-readable half of the F08
run manifest (the committed half is docs/results/F08-ablations.md). Every row carries
seed, config fingerprint, budget and W&B id; the row exists with status "running"
before the first step, so an interrupted run is visible instead of silent — the
restart-from-zero resume policy stays honest. Crash-safe atomic writes, like the
gate log.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


class RunLedger:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._rows: dict[str, dict] = {}
        if self._path.exists():
            self._rows = json.loads(self._path.read_text())["runs"]

    def record_start(self, *, run_id: str, kind: str, seed: int, fingerprint: str,
                     budget_steps: int, wandb_run_id: str | None) -> None:
        # a same-day restart of an interrupted run lands on the same id; the counter
        # keeps the first attempt visible instead of silently overwriting it
        attempts = self._rows.get(run_id, {}).get("attempts", 0) + 1
        self._rows[run_id] = {
            "attempts": attempts,
            "kind": kind,
            "seed": seed,
            "fingerprint": fingerprint,
            "budget_steps": budget_steps,
            "wandb_run_id": wandb_run_id,
            "status": "running",
            "exit_reason": None,
            "selected_step": None,
            "selected_points": None,
            "run_dir": None,
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
        }
        self._write()

    def record_complete(self, *, run_id: str, exit_reason: str,
                        selected_step: int | None = None,
                        selected_points: float | None = None,
                        run_dir: str | None = None) -> None:
        row = self._row(run_id)
        row.update(
            status="complete", exit_reason=exit_reason, selected_step=selected_step,
            selected_points=selected_points, run_dir=run_dir,
            completed_at=datetime.now(UTC).isoformat(),
        )
        self._write()

    def annotate(self, run_id: str, **fields) -> None:
        """Merge extra facts into a row — promotion marks and rescores land here."""
        self._row(run_id).update(fields)
        self._write()

    def rows(self) -> dict:
        return dict(self._rows)

    def _row(self, run_id: str) -> dict:
        if run_id not in self._rows:
            raise KeyError(f"run '{run_id}' was never started — record_start first")
        return self._rows[run_id]

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"schema_version": 1, "runs": self._rows}, indent=2))
        os.replace(tmp, self._path)


def close_run(ledger: RunLedger, run_id: str, run_dir: Path, *, stage: str) -> None:
    """Complete a ledger row from what the run left on disk: the final manifest's
    exit reason and the gate log's recorded selection, if the stage made one."""
    manifest = json.loads((Path(run_dir) / f"stage{stage}" / "final" / "manifest.json")
                          .read_text())
    gates = json.loads((Path(run_dir) / "curriculum_gates.json").read_text())
    selected = gates["stages"].get(stage, {}).get("selected_checkpoint") or {}
    ledger.record_complete(
        run_id=run_id, exit_reason=manifest["stage_exit_reason"],
        selected_step=selected.get("step"), selected_points=selected.get("mean_points"),
        run_dir=str(run_dir),
    )
