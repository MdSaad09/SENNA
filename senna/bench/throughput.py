"""Throughput benchmark (5.6.2): env steps/second across N SubprocVecEnv workers — the one
number that prices the whole training plan. The env is pure Python + NumPy, so CPU
parallelism is the throughput lever, and 8M steps is cheap only if this number is high.
Below ~300 steps/s the guidance is to profile the env (per-step object churn, pandas in
the hot loop) before trusting any schedule — and to tell Saad, because the F07 plan
changes.

Random-legal actions drive it, with the per-step action-mask fetch on the clock, so the
env is priced exactly as MaskablePPO will drive it (the mask transport is real training
cost). Policy inference is excluded — this measures the env, not the net.

    python -m senna.bench.throughput --workers 12 --steps 100000
"""

import argparse
import platform
import subprocess
import time

import numpy as np

from senna import config
from senna.env import F1RaceEnv

# the configs an env is built from — the hash that reproduces a reading
_CONFIG_FILES = ["env", "circuits", "physics_2026", "physics_2024", "physics_params",
                 "transforms", "fits", "rivals"]


def _env_factory(circuit: str, era: str):
    def make():
        return F1RaceEnv(circuit, era)

    return make


def _random_legal_actions(masks, rng) -> np.ndarray:
    actions = np.empty((len(masks), 2), dtype=int)
    for i, mask in enumerate(masks):
        actions[i, 0] = rng.choice(np.flatnonzero(mask[:6]))
        actions[i, 1] = rng.choice(np.flatnonzero(mask[6:]))
    return actions


def _commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def run_benchmark(*, workers: int, total_steps: int, warmup_steps: int, circuit: str,
                  era: str = "2026", vec: str = "subproc") -> dict:
    from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

    vec_cls = SubprocVecEnv if vec == "subproc" else DummyVecEnv
    venv = vec_cls([_env_factory(circuit, era) for _ in range(workers)])
    rng = np.random.default_rng(0)
    try:
        venv.reset()
        for _ in range(max(0, warmup_steps // workers)):
            venv.step(_random_legal_actions(venv.env_method("action_masks"), rng))

        timed_calls = max(1, total_steps // workers)
        start = time.perf_counter()
        for _ in range(timed_calls):
            venv.step(_random_legal_actions(venv.env_method("action_masks"), rng))
        wall_s = time.perf_counter() - start
    finally:
        venv.close()

    stepped = timed_calls * workers
    steps_s = stepped / wall_s
    return {
        "steps_s_aggregate": steps_s,
        "steps_s_per_worker": steps_s / workers,
        "workers": workers,
        "total_steps": stepped,
        "warmup_steps": warmup_steps,
        "wall_s": wall_s,
        "circuit": circuit,
        "era": era,
        "policy": "random_legal",
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": _cpu_count(),
        },
        "python": platform.python_version(),
        "commit": _commit(),
        "config_hash": config.fingerprint(_CONFIG_FILES),
        "projected_8m_hours": 8_000_000 / steps_s / 3600,
    }


def _cpu_count() -> int:
    import os

    return os.cpu_count() or 0


def main() -> None:
    cfg = config.load("baselines")["bench"]
    parser = argparse.ArgumentParser(description="measure env throughput across workers (5.6.2)")
    parser.add_argument("--workers", type=int, default=cfg["workers"])
    parser.add_argument("--steps", type=int, default=cfg["total_steps"])
    parser.add_argument("--warmup", type=int, default=cfg["warmup_steps"])
    parser.add_argument("--circuit", default=cfg["circuit"])
    parser.add_argument("--era", default="2026")
    parser.add_argument("--vec", choices=["subproc", "dummy"], default="subproc")
    args = parser.parse_args()

    report = run_benchmark(
        workers=args.workers, total_steps=args.steps, warmup_steps=args.warmup,
        circuit=args.circuit, era=args.era, vec=args.vec,
    )
    _print_summary(report, floor=cfg["min_steps_s"])


def _print_summary(report: dict, *, floor: int) -> None:
    print(f"throughput: {report['steps_s_aggregate']:.0f} steps/s aggregate "
          f"({report['steps_s_per_worker']:.0f}/worker x {report['workers']} workers)")
    print(f"  {report['total_steps']} steps in {report['wall_s']:.2f}s on "
          f"{report['hardware']['platform']}")
    print(f"  projects 8M steps at ~{report['projected_8m_hours']:.2f} h")
    print(f"  config {report['config_hash'][:12]} · commit {report['commit'][:12]} · "
          f"python {report['python']}")
    if report["steps_s_aggregate"] < floor:
        print(f"\n  WARNING: below {floor} steps/s — profile the env before trusting any "
              "schedule (per-step object churn, pandas in the hot loop). The F07 plan "
              "changes; flag this to Saad.")


if __name__ == "__main__":
    main()
