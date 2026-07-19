"""curriculum_gates.json — the interpretability-contract row for the curriculum (F-21).

Thresholds are echoed verbatim so the file reads without the yaml beside it; every
eval, transition and budget stop is persisted the moment it happens (atomic
tmp+rename), so a crashed run keeps its trail. A budget_stop is recorded in its own
field and never as a transition: the honest distinction between "the gate passed" and
"the ceiling arrived first".
"""

import json
import os
from pathlib import Path


class GateLog:
    def __init__(self, path: Path, *, run_id: str, config_hash: str, seeds_fingerprint: str):
        self._path = Path(path)
        self._payload = {
            "schema_version": 1,
            "run_id": run_id,
            "config_hash": config_hash,
            "seeds_fingerprint": seeds_fingerprint,
            "stages": {},
        }
        self._write()

    def start_stage(self, stage: str, thresholds: dict) -> None:
        self._payload["stages"][stage] = {
            "thresholds": thresholds,
            "evals": [],
            "transition": None,
            "budget_stop": None,
        }
        self._write()

    def record_eval(self, stage: str, *, step: int, values: dict) -> None:
        self._stage(stage)["evals"].append({"step": step, "values": values})
        self._write()

    def record_transition(self, stage: str, *, step: int, reason: str) -> None:
        self._stage(stage)["transition"] = {"step": step, "reason": reason}
        self._write()

    def record_budget_stop(self, stage: str, *, step: int) -> None:
        self._stage(stage)["budget_stop"] = {"step": step}
        self._write()

    def record_selection(self, stage: str, *, step: int, values: dict) -> None:
        self._stage(stage)["selected_checkpoint"] = {"step": step, **values}
        self._write()

    def _stage(self, stage: str) -> dict:
        if stage not in self._payload["stages"]:
            raise KeyError(f"stage '{stage}' was never started — call start_stage first")
        return self._payload["stages"][stage]

    def _write(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._payload, indent=2))
        os.replace(tmp, self._path)
