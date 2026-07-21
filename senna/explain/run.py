"""The F09 pipeline: distill the frozen headline policy into per-head surrogates,
gate on fidelity, then explain every validation-bank race — TreeSHAP drivers against
the documented background, gradient cross-check on the true network, flip probes,
decision cards into agent_decisions (5.8.2, A-03, A-04).

    make explain                # full run: models/headline + Postgres
    python -m senna.explain.run --pairs 2000 --card-races 2 --skip-persist   # smoke
"""

import os

# arm64 landmine: torch and xgboost each bundle libomp, and two OpenMP runtimes in
# one process segfault — single-threaded OpenMP, set before either library loads
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from senna import config
from senna.data.db import database_url
from senna.env import F1RaceEnv
from senna.env.masks import build_mask
from senna.env.scenario import compound_code
from senna.explain.attributions import head_explainer, top_drivers
from senna.explain.background import stratified_background
from senna.explain.cards import build_card
from senna.explain.crosscheck import gradient_attributions, rank_correlation
from senna.explain.dataset import derived_seeds, log_episode, split_by_episode
from senna.explain.features import FEATURE_NAMES, SWEEPABLE, physical_note
from senna.explain.flip import find_flip
from senna.explain.persist import write_eval_cards
from senna.explain.surrogate import (
    distill_or_refuse,
    fit_head,
    head_probs,
    load_surrogates,
    masked_top1_and_kl,
)
from senna.train.checkpoints import load_triplet
from senna.train.evals import Sb3Policy
from senna.train.seeds import load_banks

_ERA = "2026"  # the headline model is the 2026 strategist (5.7)
_MIN_RACE_LAPS = 30  # only sizes the seed draw; shorter circuits just use more seeds


def load_headline(triplet_dir: Path):
    """The score_triplet recipe (F-23): one throwaway env for the spaces, statistics
    frozen from the triplet, and the manifest that names what we are explaining."""
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    banks = load_banks()
    circuit = next(iter(banks.stage_c_validation))
    venv = DummyVecEnv([lambda: Monitor(F1RaceEnv(circuit, _ERA))])
    model, loaded = load_triplet(Path(triplet_dir), venv)
    manifest = json.loads((Path(triplet_dir) / "manifest.json").read_text())
    return Sb3Policy(model, loaded.normalize_obs), manifest, banks


def collect_distillation(policy, circuits, *, pairs_target, seed_base, seed_floor):
    """Evaluation rollouts until the pair budget is met: deterministic head on the
    stochastic train-band env (E-06), circuits round-robin, derived seeds. The seed
    list is drawn once up front so the run is a pure function of the config; the
    margin over the naive episode count covers circuits shorter than _MIN_RACE_LAPS
    and races that end early."""
    seeds = derived_seeds(seed_base, seed_floor, pairs_target // _MIN_RACE_LAPS + 64)
    envs: dict[str, F1RaceEnv] = {}
    records = []
    episodes = 0
    for i, seed in enumerate(seeds):
        if len(records) >= pairs_target:
            break
        circuit = circuits[i % len(circuits)]
        if circuit not in envs:
            envs[circuit] = F1RaceEnv(circuit, _ERA, rival_band="train")
        records.extend(log_episode(envs[circuit], policy, circuit=circuit, seed=seed))
        episodes += 1
    if len(records) < pairs_target:
        raise RuntimeError(
            f"{len(records)} pairs from {episodes} episodes, {pairs_target} required "
            "(distill.pairs) — the seed draw ran out; a surrogate fitted on less "
            "would be a quieter model than the spec asks for"
        )
    return records, episodes


def distill_heads(train_records, holdout_records, cfg, *, seed):
    X_train = np.stack([r.obs for r in train_records])
    X_hold = np.stack([r.obs for r in holdout_records])
    ladder = config.get(cfg, "distill.xgb_ladder")
    floor = config.get(cfg, "distill.soft_label_weight_floor")
    threshold = config.get(cfg, "fidelity.threshold")

    heads = {}
    for head, n_class in (("pit", 6), ("mode", 4)):
        heads[head] = _distill_one(
            head, n_class, train_records, holdout_records, X_train, X_hold,
            ladder=ladder, weight_floor=floor, threshold=threshold, seed=seed,
        )
    return heads


def _distill_one(head, n_class, train_records, holdout_records, X_train, X_hold, *,
                 ladder, weight_floor, threshold, seed):
    probs_train = np.stack([_unmasked(r, head) for r in train_records])
    policy_hold = np.stack([_masked(r, head) for r in holdout_records])
    masks_hold = np.stack([_head_mask(r, head) for r in holdout_records])
    rungs = []

    def fit_rung(rung):
        rungs.append(rung)
        booster = fit_head(X_train, probs_train, {**rung, "weight_floor": weight_floor},
                           num_class=n_class, seed=seed)
        top1, kl = masked_top1_and_kl(head_probs(booster, X_hold), policy_hold, masks_hold)
        return booster, top1, kl

    booster, top1, mean_kl = distill_or_refuse(ladder=ladder, threshold=threshold,
                                               fit_rung=fit_rung)
    return {"booster": booster, "top1": top1, "mean_kl": mean_kl, "rung": rungs[-1]}


def _unmasked(record, head):
    return record.pit_probs_unmasked if head == "pit" else record.mode_probs_unmasked


def _masked(record, head):
    return record.pit_probs_masked if head == "pit" else record.mode_probs_masked


def _head_mask(record, head):
    return record.mask[:6] if head == "pit" else record.mask[6:]


def pit_mask_fn(scenario):
    """The env's own pit-head legality, rebuilt from a swept observation — every
    build_mask input is recoverable from the obs encoding plus scenario constants,
    so a sweep can never report a flip onto an action the mask forbids there."""
    validity = scenario.env["compound_validity"]
    fitted = frozenset(compound_code(c) + 1 for c in scenario.available_compounds)

    def from_obs(obs):
        return build_mask(
            pit_open=bool(obs[26] > 0.5),
            weather=int(np.argmax(obs[27:30])),
            wetness=float(obs[30]),
            soc_mj=float(obs[14]) * scenario.usable_soc_mj,
            lap=int(round(float(obs[0]) * scenario.total_laps)),
            total_laps=scenario.total_laps,
            second_compound_used=bool(obs[12] > 0.5),
            attack_soc_floor_mj=scenario.attack_soc_floor_mj,
            validity=validity,
            fitted_slick_actions=fitted,
        ).pit

    return from_obs


def pit_policy_fn(policy):
    """The true policy's pit call at an arbitrary state — the flip probe sweeps the
    network, not the surrogate (5.8.2). The mode head runs unmasked; it cannot
    change which pit action argmax wins."""
    mode_open = np.ones(4, dtype=bool)

    def pit_action(obs, pit_mask):
        flat = np.concatenate([np.asarray(pit_mask, dtype=bool), mode_open])
        action, _ = policy.model.predict(policy.normalize_obs(obs), action_masks=flat,
                                         deterministic=True)
        return int(action[0])

    return pit_action


def flip_lines_for(record, pit_top, scenario, policy_fn, mask_fn, *, per_card,
                   sweep_points):
    lines = []
    dim_of = {name: i for i, name in enumerate(FEATURE_NAMES)}
    for name, _ in pit_top:
        if len(lines) == per_card:
            break
        bounds = SWEEPABLE.get(dim_of[name])
        if bounds is None:
            continue  # a one-hot drove the call; there is nothing honest to sweep
        grid = np.asarray(bounds) if len(bounds) == 3 else np.linspace(*bounds, sweep_points)
        flip_at = find_flip(policy_fn, record.obs, dim_of[name], grid, mask_fn)
        if flip_at is None:
            continue
        note = physical_note(dim_of[name], flip_at, scenario)
        suffix = f" ({note})" if note else ""
        lines.append(f"the call flips if {name} crossed {flip_at:.2f}{suffix}")
    if not lines:
        lines.append("no single sweepable feature flips this call within its physical range")
    return lines


def race_cards(policy, env, circuit, seed, explainers, cfg, *, fidelity,
               model_version, surrogate_version):
    records = log_episode(env, policy, circuit=circuit, seed=seed)
    X = np.stack([r.obs for r in records])
    pit_shap = explainers["pit"].shap_values(X)
    mode_shap = explainers["mode"].shap_values(X)

    top_k = config.get(cfg, "cards.top_k_drivers")
    per_card = config.get(cfg, "flip.features_per_card")
    sweep_points = config.get(cfg, "flip.sweep_points")
    mask_fn = pit_mask_fn(env.scenario)
    policy_fn = pit_policy_fn(policy)

    cards = []
    for i, record in enumerate(records):
        pit_top = top_drivers(pit_shap[i, :, record.pit_action], FEATURE_NAMES, top_k)
        mode_top = top_drivers(mode_shap[i, :, record.mode_action], FEATURE_NAMES, top_k)
        flips = flip_lines_for(record, pit_top, env.scenario, policy_fn, mask_fn,
                               per_card=per_card, sweep_points=sweep_points)
        cards.append(build_card(
            record, pit_drivers=pit_top, mode_drivers=mode_top, flip_lines=flips,
            fidelity=fidelity, model_version=model_version,
            surrogate_version=surrogate_version,
        ))
    return cards, records


def run_crosscheck(policy, card_records, explainers, background, cfg, *, seed):
    sample = config.get(cfg, "crosscheck.sample")
    subsample = config.get(cfg, "crosscheck.background_subsample")
    if len(card_records) < sample:
        raise ValueError(
            f"only {len(card_records)} decisions to cross-check, {sample} required "
            "(crosscheck.sample) — the integrity statistic would be measured on less "
            "than the spec asks for; card more races"
        )
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(card_records), size=sample, replace=False)
    X = np.stack([card_records[i].obs for i in picks])
    chosen = [card_records[i].pit_action for i in picks]

    tree_vals = explainers["pit"].shap_values(X)
    bg = background[rng.choice(len(background), size=min(subsample, len(background)),
                               replace=False)]
    grad_vals = gradient_attributions(policy.model, policy.normalize_obs, X, bg, "pit")
    rhos = np.asarray([
        rank_correlation(np.abs(tree_vals[j, :, a]), np.abs(grad_vals[j, :, a]))
        for j, a in enumerate(chosen)
    ])
    return float(rhos.mean()), rhos


def write_surrogate_artifacts(dest: Path, *, heads, background, composition,
                              holdout_records, model_version: str):
    """Everything the cards are built from, written before a single card exists —
    the manifest is then what names the checkpoint being explained, so card
    generation reads the version off disk instead of trusting a variable (E-15).
    The manifest is removed first and written last: a run that dies mid-write
    leaves no stale manifest whose hashes describe boosters that are gone."""
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / "manifest.json"
    manifest_path.unlink(missing_ok=True)

    for head in ("pit", "mode"):
        heads[head]["booster"].save_model(str(dest / f"{head}.ubj"))
    np.savez_compressed(dest / "background.npz", states=background)
    (dest / "background_composition.json").write_text(json.dumps(composition, indent=2))
    np.savez_compressed(
        dest / "holdout.npz",
        obs=np.stack([r.obs for r in holdout_records]),
        pit_probs_masked=np.stack([r.pit_probs_masked for r in holdout_records]),
        mode_probs_masked=np.stack([r.mode_probs_masked for r in holdout_records]),
        masks=np.stack([r.mask for r in holdout_records]),
    )
    manifest_path.write_text(json.dumps({
        "model_version": model_version,
        "pit_ubj_sha256": _sha256(dest / "pit.ubj"),
        "mode_ubj_sha256": _sha256(dest / "mode.ubj"),
        "git_commit": _git_commit(),
        "saved_at": datetime.now(UTC).isoformat(),
    }, indent=2))


def write_readout(dest: Path, *, fidelity_payload, rhos):
    """The numbers, once the cards and the cross-check have produced them."""
    np.savez_compressed(dest / "crosscheck.npz", pit_spearman_rho=rhos)
    (dest / "fidelity.json").write_text(json.dumps(fidelity_payload, indent=2))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="distill, explain and card the frozen headline model (F09)"
    )
    parser.add_argument("--triplet", type=Path, default=Path("models/headline"))
    parser.add_argument("--pairs", type=int, default=None,
                        help="dev cap: override distill.pairs for a smoke run")
    parser.add_argument("--card-races", type=int, default=None,
                        help="dev cap: card only the first N validation races")
    parser.add_argument("--skip-persist", action="store_true",
                        help="dev: skip the agent_decisions write")
    args = parser.parse_args()

    cfg = config.load("explain")
    policy, manifest, banks = load_headline(args.triplet)
    model_version = manifest["model_version"]
    env_config_hash = manifest["fingerprint"]
    circuits = sorted(banks.stage_c_validation)
    seed_base = config.get(cfg, "distill.rollout_seed_base")
    print(f"explaining {model_version} (config {env_config_hash[:12]})")

    records, episodes = collect_distillation(
        policy, circuits,
        pairs_target=args.pairs or config.get(cfg, "distill.pairs"),
        seed_base=seed_base, seed_floor=config.get(cfg, "distill.seed_floor"),
    )
    train, holdout = split_by_episode(
        records, config.get(cfg, "distill.holdout_episode_frac"), seed=seed_base
    )
    n_pairs = len(records)
    del records  # 200k records is a few hundred MB; the split owns them from here
    print(f"distillation: {n_pairs} pairs from {episodes} episodes "
          f"({len(holdout)} held out at episode level)")

    heads = distill_heads(train, holdout, cfg, seed=seed_base)
    for head, fit in heads.items():
        print(f"  {head}: top-1 {fit['top1']:.3f}, mean KL {fit['mean_kl']:.4f} "
              f"(depth {fit['rung']['max_depth']}, {fit['rung']['n_estimators']} trees)")

    thresholds = config.get(cfg, "background.phase_thresholds")
    background, composition = stratified_background(
        train, config.get(cfg, "background.size"),
        early=thresholds["early"], late=thresholds["late"], seed=seed_base,
    )

    dest = Path("models/explain") / model_version
    write_surrogate_artifacts(dest, heads=heads, background=background,
                              composition=composition, holdout_records=holdout,
                              model_version=model_version)
    # read the version back out of the artifact the cards are about to be built
    # from: a stale models/explain/ is then caught by build_card, not trusted (E-15)
    _, surrogate_version = load_surrogates(dest)
    explainers = {head: head_explainer(fit["booster"], background)
                  for head, fit in heads.items()}
    fidelity = {head: fit["top1"] for head, fit in heads.items()}

    race_list = [(c, s) for c in circuits for s in banks.stage_c_validation[c]]
    if args.card_races:
        race_list = race_list[:args.card_races]
    envs: dict[str, F1RaceEnv] = {}
    races, card_records = [], []
    for circuit, seed in race_list:
        if circuit not in envs:
            envs[circuit] = F1RaceEnv(circuit, _ERA, rival_band="train")
        cards, recs = race_cards(
            policy, envs[circuit], circuit, seed, explainers, cfg, fidelity=fidelity,
            model_version=model_version, surrogate_version=surrogate_version,
        )
        races.append({"circuit": circuit, "seed": seed, "cards": cards})
        card_records.extend(recs)
    print(f"cards: {sum(len(r['cards']) for r in races)} across {len(races)} races")

    rho_mean, rhos = run_crosscheck(policy, card_records, explainers, background, cfg,
                                    seed=seed_base)
    print(f"cross-check: mean Spearman rho {rho_mean:.3f} over {len(rhos)} decisions")

    fidelity_payload = {
        "model_version": model_version,
        "env_config_hash": env_config_hash,
        "threshold": config.get(cfg, "fidelity.threshold"),
        "heads": {
            head: {"top1": fit["top1"], "mean_kl": fit["mean_kl"], "rung": fit["rung"]}
            for head, fit in heads.items()
        },
        "pairs": n_pairs,
        "episodes": episodes,
        "holdout_pairs": len(holdout),
        "crosscheck": {"mean_spearman_rho": rho_mean, "sample": int(len(rhos))},
        "cards": sum(len(r["cards"]) for r in races),
        "card_races": len(races),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    write_readout(dest, fidelity_payload=fidelity_payload, rhos=rhos)
    print(f"artifacts: {dest}")

    if args.skip_persist:
        print("persist skipped (dev)")
        return
    write_eval_cards(database_url(), model_version, env_config_hash, races)
    print(f"persisted to agent_decisions as {model_version}")


if __name__ == "__main__":
    main()
