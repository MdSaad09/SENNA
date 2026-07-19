"""The tracking seam: everything W&B goes through a Tracker, and wandb is imported in
this module only (F-26 — training-side, never serving; the sibling of the
fastf1-under-senna/data rule). A run without an account degrades to offline, a
disabled or failed init degrades to the no-op base, and tests inject a recording
subclass — training never crashes because of telemetry.
"""

import os
import warnings


class Tracker:
    """No-op base. The real tracker overrides all three; tests record through log."""

    def log(self, series: dict, *, step: int) -> None:
        pass

    def set_summary(self, mapping: dict) -> None:
        pass

    def finish(self) -> None:
        pass


class _WandbTracker(Tracker):
    def __init__(self, run):
        self._run = run

    def log(self, series: dict, *, step: int) -> None:
        self._run.log(series, step=step)

    def set_summary(self, mapping: dict) -> None:
        for key, value in mapping.items():
            self._run.summary[key] = value

    def finish(self) -> None:
        self._run.finish()


def make_tracker(*, mode: str, project: str, run_name: str, group: str,
                 config: dict) -> Tracker:
    """mode: auto | online | offline | disabled. auto goes online only when
    WANDB_API_KEY is set, so a machine with no account still trains and syncs later."""
    if mode == "auto":
        mode = "online" if os.environ.get("WANDB_API_KEY") else "offline"
    if mode == "disabled":
        return Tracker()

    import wandb

    try:
        run = wandb.init(
            project=project, name=run_name, group=group, mode=mode, config=config
        )
    except Exception as error:  # telemetry must never kill a training run
        warnings.warn(f"wandb.init failed ({error}); continuing without tracking",
                      stacklevel=2)
        return Tracker()
    return _WandbTracker(run)


def sb3_output_format(tracker: Tracker):
    """An SB3 KVWriter that forwards every logger dump (rollout/*, train/*, time/*)
    to the tracker, replacing the tensorboard route wandb's stock callback needs."""
    from stable_baselines3.common.logger import KVWriter

    class _TrackerFormat(KVWriter):
        def write(self, key_values: dict, key_excluded: dict, step: int = 0) -> None:
            numeric = {
                key: float(value) for key, value in key_values.items()
                if isinstance(value, (int, float))
            }
            if numeric:
                tracker.log(numeric, step=step)

        def close(self) -> None:
            pass

    return _TrackerFormat()
