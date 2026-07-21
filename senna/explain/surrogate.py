"""Distillation (A-04): one XGBoost multi-class model per action head, fitted to the
policy's unmasked probabilities by weighted row expansion — each state appears once
per action it gives real mass, weight = that probability, which minimises the same
soft-target cross-entropy as a bespoke distillation objective on stock
multi:softprob. Fidelity is scored the way cards will use the surrogate: masked to
the legal actions and renormalised, never on the raw distribution. Below the 0.90
bar the pipeline refuses — the gate is code, not intention (feature spec row one).
"""

import numpy as np


class FidelityGateError(RuntimeError):
    """Every ladder rung missed the fidelity threshold — no cards ship (5.8.2)."""


def expand_soft_labels(X, probs, weight_floor: float):
    """Soft targets as weighted hard rows. Zero-mass actions never become rows, and
    rows lighter than the floor are dropped — they add trees, not fidelity."""
    X = np.asarray(X)
    probs = np.asarray(probs)
    keep = probs >= weight_floor
    state_idx, labels = np.nonzero(keep)
    return X[state_idx], labels.astype(np.int64), probs[keep].astype(np.float64)


def masked_top1_and_kl(surrogate_probs, policy_masked_probs, masks):
    """Fidelity as the cards consume it: the surrogate's distribution masked to the
    legal actions and renormalised, then top-1 agreement with the policy's own
    masked choice and mean KL(policy || surrogate) over the legal actions. The KL
    runs policy-first — the policy puts exact zeros on masked actions, and those
    terms contribute nothing; the reverse direction would divide by them."""
    surrogate = np.where(masks, np.asarray(surrogate_probs, dtype=np.float64), 0.0)
    row_mass = surrogate.sum(axis=1, keepdims=True)
    if np.any(row_mass == 0.0):
        raise ValueError("a surrogate row has no mass on any legal action")
    surrogate /= row_mass

    policy = np.asarray(policy_masked_probs, dtype=np.float64)
    top1 = float(np.mean(surrogate.argmax(axis=1) == policy.argmax(axis=1)))

    support = policy > 0.0
    ratios = np.divide(policy, surrogate, out=np.ones_like(policy), where=support)
    mean_kl = float(np.mean(np.sum(policy * np.log(ratios), axis=1, where=support)))
    return top1, mean_kl


def distill_or_refuse(*, ladder, threshold: float, fit_rung):
    """Walk the deepen ladder shallow to deep (5.8.2: "deepen the surrogate before
    shipping explanations"); return the first rung that clears the bar, refuse after
    the last. fit_rung(rung) -> (surrogate, top1, mean_kl)."""
    if not ladder:
        raise ValueError("distill.xgb_ladder is empty — there is nothing to fit")
    best = 0.0
    for rung in ladder:
        surrogate, top1, mean_kl = fit_rung(rung)
        if top1 >= threshold:
            return surrogate, top1, mean_kl
        best = max(best, top1)
    raise FidelityGateError(
        f"best fidelity {best:.3f} across {len(ladder)} rungs, threshold {threshold} "
        "— no cards ship from this surrogate; deepen the ladder in "
        "configs/explain.yaml or revisit the distillation data"
    )


def fit_head(X_train, probs_train, rung: dict, *, num_class: int, seed: int):
    """One rung: train the head's booster on the expanded soft targets. The explicit
    base_score keeps TreeSHAP additivity exact — xgboost 3.x otherwise fits an
    intercept the explainer would have to guess."""
    import xgboost as xgb

    floor = rung["weight_floor"]
    X_rows, labels, weights = expand_soft_labels(X_train, probs_train, floor)
    booster = xgb.train(
        {
            "objective": "multi:softprob",
            "num_class": num_class,
            "max_depth": rung["max_depth"],
            "eta": rung["learning_rate"],
            "base_score": 0.5,
            "seed": seed,
            "nthread": 1,  # the arm64 OpenMP clash (F09 plan); the models are tiny
        },
        xgb.DMatrix(X_rows, label=labels, weight=weights),
        num_boost_round=rung["n_estimators"],
    )
    return booster


def head_probs(booster, X) -> np.ndarray:
    import xgboost as xgb

    return booster.predict(xgb.DMatrix(np.asarray(X)))


def load_surrogates(artifacts_dir):
    """Rehydrate the boosters and the checkpoint they were fitted to. Reading the
    version back off disk rather than passing it along in memory is what makes the
    E-15 refusal real: cards are built against what the artifact says it explains,
    so a stale models/explain/ directory is caught instead of trusted."""
    import json
    from pathlib import Path

    import xgboost as xgb

    artifacts_dir = Path(artifacts_dir)
    heads = {}
    for head in ("pit", "mode"):
        booster = xgb.Booster()
        booster.load_model(str(artifacts_dir / f"{head}.ubj"))
        heads[head] = booster
    manifest = json.loads((artifacts_dir / "manifest.json").read_text())
    return heads, manifest["model_version"]
