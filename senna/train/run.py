

import argparse
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from senna import config
from senna.train.callbacks import (
    GateEvalCallback,
    RewardTermsCallback,
    ScheduleCallback,
    ThroughputCallback,
)
from senna.train.checkpoints import model_version, save_triplet
from senna.train.envs import assign_circuits, stage_venv
from senna.train.evals import (
    Sb3Policy,
    record_stage_b_traces,
    run_stage_a_eval,
    run_stage_b_eval,
    run_stage_c_eval,
    stage_a_reference,
)
from senna.train.gatelog import GateLog
from senna.train.gates import (
    GateDecision,
    select_checkpoint,
    stage_a_gate,
    stage_b_gate,
    stage_c_stop,
)
from senna.train.model import build_model
from senna.train.seeds import load_banks
from senna.train.tracking import make_tracker, sb3_output_format

STAGES = ("A", "B", "C")

# the exact configs a run is reproducible from — the bench's env list plus F07's own.
# The ablation harness appends "ablations" for its runs only (extra_config_files), so
# the headline's fingerprint can never be broken by a later coefficient edit there.
CONFIG_FILES = ["env", "circuits", "physics_2026", "physics_2024", "physics_params",
                "transforms", "fits", "rivals", "training", "curriculum", "seeds"]


def run_identity(*, seed: int, fingerprint: str, run_tag: str | None = None) -> str:
   
    tag = f"{run_tag}-" if run_tag else ""
    return f"{tag}{datetime.now(UTC):%Y%m%d}-s{seed}-{fingerprint[:12]}"


def build_evaluator(stage: str, stage_cfg: dict, *, model, venv, banks, gate_log,
                    plateau_floor: float, run_dir: Path, configs_dir=None):
   
    policy = Sb3Policy(model, venv.normalize_obs)
    gate = stage_cfg["gate"]
    era = stage_cfg.get("era", "2026")  # only the F14 era-matched overlay sets this

    if stage == "A":
        circuit = stage_cfg["circuits"][0]
        _, reference_time_s = stage_a_reference(circuit, configs_dir=configs_dir, era=era)
        history = []

        def evaluate(step):
            history.append(run_stage_a_eval(
                policy, step=step, circuit=circuit, seeds=banks.stage_a,
                configs_dir=configs_dir, era=era,
            ))
            decision = stage_a_gate(
                history, reference_time_s=reference_time_s,
                plateau_window=gate["plateau_window"],
                plateau_min_improvement=gate["plateau_min_improvement"],
                time_tolerance=gate["time_tolerance"], denominator_floor=plateau_floor,
            )
            gate_log.record_eval(stage, step=step, values={
                **decision.values, "mean_return": history[-1].mean_return,
                "passed": decision.passed,
            })
            return decision

        return evaluate

    if stage == "B":
        traces_dir = run_dir / "stage_b_traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        recorded, replaced = record_stage_b_traces(
            banks=banks.stage_b, overflow=banks.stage_b_overflow,
            configs_dir=configs_dir, traces_dir=traces_dir, era=era,
        )
        gate_log.record_recording(stage, replaced_seeds=replaced,
                                  traces_dir=str(traces_dir))

        replay_envs = {}  # built once; a gate check replays 200 races across six circuits

        def evaluate(step):
            pairs = run_stage_b_eval(policy, recorded, configs_dir=configs_dir,
                                     env_cache=replay_envs, era=era)
            decision = stage_b_gate(
                pairs, finish_ahead_min=gate["finish_ahead_min"],
                median_delta_min=gate["median_delta_min"], n_required=gate["n_pairs"],
            )
            gate_log.record_eval(stage, step=step,
                                 values={**decision.values, "passed": decision.passed})
            return decision

        return evaluate

    history = []
    eval_envs = {}  # 24 circuits' worth of yaml parsing, paid once per run

    def evaluate(step):
        history.append(run_stage_c_eval(
            policy, step=step, banks=banks.stage_c_validation, configs_dir=configs_dir,
            env_cache=eval_envs, era=era, circuits=stage_cfg["circuits"],
        ))
        decision = stage_c_stop(
            history, current_step=step, stagnation_steps=gate["stagnation_steps"],
            min_improvement_points=gate["min_improvement_points"],
        )
        values = {
            **decision.values, "mean_points": history[-1].mean_points,
            "improved": decision.values["best_step"] == step, "passed": decision.passed,
        }
        gate_log.record_eval(stage, step=step, values=values)
        return GateDecision(decision.passed, decision.reason, values)

    evaluate.history = history  # the loop selects the checkpoint from it (5.7)
    return evaluate


def train_run(*, seed: int, from_stage: str = "A", to_stage: str = "C",
              resume: Path | None = None, total_steps: int | None = None,
              workers: int | None = None, vec: str = "subproc",
              wandb_mode: str = "auto", configs_dir=None, tracker=None,
              models_dir=None, fresh: bool = False, run_tag: str | None = None,
              run_id: str | None = None, extra_config_files: tuple = ()) -> Path:
    from stable_baselines3.common.logger import Logger
    from stable_baselines3.common.utils import set_random_seed

    train_cfg = config.load("training", configs_dir)
    curriculum = config.load("curriculum", configs_dir)
    stage_offset = config.load("seeds", configs_dir)["train"]["stage_offset"]
    banks = load_banks(configs_dir)
    config_files = [*CONFIG_FILES, *extra_config_files]
    fingerprint = config.fingerprint(config_files, configs_dir)

    workers = workers or train_cfg["ppo"]["n_envs"]
    if STAGES.index(from_stage) > STAGES.index(to_stage):
        raise ValueError(f"stage span {from_stage}->{to_stage} is empty")
    stages = STAGES[STAGES.index(from_stage): STAGES.index(to_stage) + 1]
    if from_stage != "A" and resume is None and not fresh:
        # fresh=True is the no-curriculum ablation's door (5.6.3 row 1); everyone
        # else starting past A without a triplet is an accident
        raise ValueError(f"starting at stage {from_stage} needs --resume <triplet dir>"
                         " (or --fresh for a from-scratch ablation run)")
    if total_steps is not None:
        print(f"DEV CAP: every stage budget clipped to {total_steps} steps — "
              "not a real training run")

    run_id = run_id or run_identity(seed=seed, fingerprint=fingerprint, run_tag=run_tag)
    run_dir = Path(models_dir or config.REPO_ROOT / "models") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if tracker is None:
        tracker = make_tracker(
            mode=wandb_mode, project=train_cfg["tracking"]["project"],
            run_name=f"{run_tag or 'train'}-s{seed}-{fingerprint[:12]}",
            group=fingerprint[:12],
            config={"seed": seed, "fingerprint": fingerprint, "stages": list(stages),
                    "training": train_cfg, "curriculum": curriculum},
            tags=[run_tag] if run_tag else None,
        )
    gate_log = GateLog(
        run_dir / "curriculum_gates.json", run_id=run_id, config_hash=fingerprint,
        seeds_fingerprint=config.fingerprint(["seeds"], configs_dir),
    )

    set_random_seed(seed)
    # the summed ceilings, always over the full curriculum: a resumed stage B keeps
    # the same decay line an uninterrupted run would have had
    horizon = sum(curriculum["stages"][s]["budget_steps"] for s in STAGES)
    ppo = train_cfg["ppo"]

    model = None
    reward_terms = RewardTermsCallback()
    stats_path = Path(resume) / "vecnormalize.pkl" if resume else None
    for stage in stages:
        stage_cfg = curriculum["stages"][stage]
        venv = stage_venv(
            stage_cfg, workers=workers, stage_seed=seed + stage_offset[stage], vec=vec,
            normalize=train_cfg["normalize"], stats_path=stats_path,
            configs_dir=configs_dir,
        )
        if model is None:
            if resume:
                from sb3_contrib import MaskablePPO

                model = MaskablePPO.load(Path(resume) / "model.zip", env=venv,
                                         device="cpu")
            else:
                model = build_model(train_cfg, venv, seed=seed)
            model.set_logger(Logger(folder=None, output_formats=[sb3_output_format(tracker)]))
        else:
            model.set_env(venv, force_reset=True)
        # the ctor and load paths call set_random_seed, which re-seeds the env with the
        # run seed — re-issue the stage seed so the disjoint-stream design (seeds.yaml
        # train.stage_offset) and the manifest's stage_seed entry stay true
        venv.seed(seed + stage_offset[stage])

        stage_dir = run_dir / f"stage{stage}"
        tracker.log({"curriculum/stage": STAGES.index(stage)}, step=model.num_timesteps)
        gate_log.start_stage(stage, {**stage_cfg["gate"],
                                     "budget_steps": stage_cfg["budget_steps"],
                                     "eval_every_steps": stage_cfg["eval_every_steps"]})
        evaluate = build_evaluator(
            stage, stage_cfg, model=model, venv=venv, banks=banks, gate_log=gate_log,
            plateau_floor=curriculum["plateau_denominator_floor"], run_dir=run_dir,
            configs_dir=configs_dir,
        )

        # keyword defaults pin this stage's objects: the loop rebinds these names next
        # stage, and a late-bound closure would silently checkpoint the wrong stage
        def manifest(step, exit_reason=None, *, stage=stage, stage_cfg=stage_cfg,
                     resumed=resume):
            return {
                "model_version": model_version(fingerprint, stage, step),
                "run_id": run_id,
                "run_tag": run_tag,
                # the serving registry resolves a triplet by era (F-24); without it the
                # counterfactual route cannot tell the era-matched model from the headline
                "era": stage_cfg.get("era", "2026"),
                "fingerprint": fingerprint,
                "config_files": config_files,
                "git_commit": _git_commit(),
                "stage": stage,
                "global_step": step,
                "stage_exit_reason": exit_reason,
                "seed": seed,
                "stage_seed": seed + stage_offset[stage],
                "circuit_assignment": {
                    str(i): circuits for i, circuits in
                    enumerate(assign_circuits(stage_cfg["circuits"], workers))
                },
                "dominance_ratio": reward_terms.run_dominance_ratio(),
                "wandb_run_id": getattr(tracker, "run_id", None),
                "versions": _versions(),
                "resumed_from": str(resumed) if resumed else None,
                "saved_at": datetime.now(UTC).isoformat(),
            }

        def save_to(name, step, exit_reason=None, *, model=model, venv=venv,
                    stage_dir=stage_dir, manifest=manifest):
            save_triplet(model, venv, stage_dir / name,
                         manifest=manifest(step, exit_reason))

        gate_cb = GateEvalCallback(
            evaluate, every_steps=stage_cfg["eval_every_steps"], tracker=tracker,
            save_last=lambda step, save_to=save_to: save_to("last", step),
            save_best=(
                (lambda step, save_to=save_to: save_to("best", step))
                if stage == "C" else None
            ),
        )
        budget = stage_cfg["budget_steps"]
        if total_steps is not None:
            budget = min(budget, total_steps)
        print(f"stage {stage}: {budget:,}-step ceiling, "
              f"eval every {stage_cfg['eval_every_steps']:,}")
        model.learn(
            total_timesteps=budget, reset_num_timesteps=False,
            callback=[
                ScheduleCallback(lr=(ppo["learning_rate"]["start"], ppo["learning_rate"]["end"]),
                                 ent=(ppo["ent_coef"]["start"], ppo["ent_coef"]["end"]),
                                 horizon_steps=horizon),
                reward_terms, ThroughputCallback(), gate_cb,
            ],
        )

        step_now = model.num_timesteps
        # a gate pass aborts learn() mid-collection, leaving the last update's train/*
        # records undumped — flush them so the run's telemetry ends where the stage did
        model.logger.dump(step=step_now)
        if not gate_cb.passed and gate_cb.last_eval_step != step_now:
            gate_cb.run_eval()  # a ceiling exit still gets a real, logged evaluation
        if gate_cb.passed:
            exit_reason = "gate"
            gate_log.record_transition(stage, step=gate_cb.last_eval_step,
                                       reason=gate_cb.decision.reason)
        else:
            exit_reason = "ceiling"
            gate_log.record_budget_stop(stage, step=step_now)
        print(f"stage {stage}: exit by {exit_reason} at step {step_now:,} — "
              f"{gate_cb.decision.reason}")

        if stage == "C" and getattr(evaluate, "history", None):
            best = select_checkpoint(evaluate.history)
            gate_log.record_selection(stage, step=best.step,
                                      values={"mean_points": best.mean_points})

        save_triplet(model, venv, stage_dir / "final",
                     manifest=manifest(step_now, exit_reason))
        # carry_across_stages False is F08's re-warm ablation: each stage then starts
        # with fresh statistics instead of the previous stage's
        stats_path = (stage_dir / "final" / "vecnormalize.pkl"
                      if train_cfg["normalize"]["carry_across_stages"] else None)
        resume = None  # only the first trained stage warm-starts from the CLI triplet
        venv.close()

    tracker.set_summary({
        "dominance_ratio": reward_terms.run_dominance_ratio(),
        "final_step": model.num_timesteps,
        "run_dir": str(run_dir),
    })
    tracker.finish()
    return run_dir


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def _versions() -> dict:
    import sb3_contrib
    import stable_baselines3
    import torch

    return {
        "stable_baselines3": stable_baselines3.__version__,
        "sb3_contrib": sb3_contrib.__version__,
        "torch": torch.__version__,
        "python": platform.python_version(),
    }


def main() -> None:
    headline = config.load("seeds")["train"]["headline"]
    parser = argparse.ArgumentParser(description="train the curriculum A->B->C (5.6.1, 5.7)")
    parser.add_argument("--seed", type=int, default=headline[0])
    parser.add_argument("--from-stage", choices=STAGES, default="A")
    parser.add_argument("--to-stage", choices=STAGES, default="C")
    parser.add_argument("--resume", type=Path, default=None,
                        help="triplet dir to warm-start from (required past stage A)")
    parser.add_argument("--fresh", action="store_true",
                        help="allow a from-scratch start past stage A (5.6.3 row 1)")
    parser.add_argument("--run-tag", default=None,
                        help="prefix for the run id and W&B name (the harness sets it)")
    parser.add_argument("--total-steps", type=int, default=None,
                        help="dev cap per stage — smoke runs only")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--vec", choices=["subproc", "dummy"], default="subproc")
    parser.add_argument("--wandb-mode", choices=["auto", "online", "offline", "disabled"],
                        default="auto")
    args = parser.parse_args()

    run_dir = train_run(
        seed=args.seed, from_stage=args.from_stage, to_stage=args.to_stage,
        resume=args.resume, total_steps=args.total_steps, workers=args.workers,
        vec=args.vec, wandb_mode=args.wandb_mode, fresh=args.fresh,
        run_tag=args.run_tag,
    )
    print(f"run complete: {run_dir}")
    print(json.dumps(json.loads((run_dir / "curriculum_gates.json").read_text()), indent=2)[:2000])


if __name__ == "__main__":
    main()
