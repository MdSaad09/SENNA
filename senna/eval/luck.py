"""M11 / A-08 — the luck-share decomposition: how much of a finishing position the event
draw explains, and how much the decisions do.

Two things make this metric subtle enough to state carefully.

The served policy is deterministic, so under a fixed event seed it produces one outcome
and there is no decision variance to decompose at all. A split only exists relative to
some distribution over decisions, and the honest choice is the policy's own head — the
preferences it actually learned, sampled rather than argmaxed. Mean head entropy is
reported beside the share so a reader can see how wide that probe was.

And because the env consumes randomness policy-dependently, re-sampled decisions do not
meet the same events: a different stop draws a different service time and the race
diverges from there. That entangled variance is charged to the decision side. The
defensible reading is that between-seed variance is what survives re-sampling the
decisions — no choice removes it on average — which makes the published share a
conservative lower bound on what the event draws explain. Overstating luck would flatter
the novelty; understating it costs nothing but a footnote.

Decision reps are nested inside event seeds rather than crossed with them. The same torch
seed consumes its variates differently under a different observation sequence, so "rep 3"
names nothing shared across two races and a two-way ANOVA's rep main effect would be an
artefact of the numbering.
"""

import numpy as np

from senna.eval.bootstrap import mean_interval


def decision_seed(event_seed: int, rep: int, *, stream: int) -> int:
    """A reproducible decision seed for one (race, repetition). SeedSequence spreads the
    three inputs, so neighbouring reps do not produce neighbouring streams."""
    return int(np.random.SeedSequence([int(event_seed), int(rep), int(stream)])
               .generate_state(1)[0])


class StochasticSb3Policy:
    """The served network sampling its masked head instead of taking the argmax. Masks
    still bind — legality is structural (A-01), and a decision probe that could propose
    an illegal action would be measuring the wrong distribution."""

    def __init__(self, model, normalize_obs, *, decision_seed: int):
        self.model = model
        self.normalize_obs = normalize_obs
        self.decision_seed = int(decision_seed)
        self.head_entropies: list[float] = []

    def reset(self, obs, info, *, rng=None) -> None:
        self.model.set_random_seed(self.decision_seed)
        self.head_entropies = []

    def act(self, obs, info, mask) -> np.ndarray:
        observation = self.normalize_obs(obs)
        masks = np.asarray(mask)
        action, _ = self.model.predict(
            observation, action_masks=masks, deterministic=False
        )
        entropy = _masked_head_entropy(self.model, observation, masks)
        if entropy is not None:
            self.head_entropies.append(entropy)
        return action

    @property
    def mean_head_entropy(self) -> float:
        """How wide the probe was, in nats per decision, over the episode just rolled.
        nan when nothing was recorded, which reads as "unknown" rather than "collapsed"."""
        return float(np.mean(self.head_entropies)) if self.head_entropies else float("nan")


def _masked_head_entropy(model, obs, mask) -> float | None:
    """Entropy of the masked joint head — pit plus mode, in nats — for the one decision
    predict() just sampled. Every decision is measured rather than sub-sampled: this is a
    second forward pass through a small MLP, which does not register next to the lap the
    env then simulates for it.

    None when the model carries no SB3 policy, as a stand-in in tests does not. M11's
    decomposition is the metric and the entropy is the context printed beside it; context
    that can take a six-hour eval run down is worse than no context.
    """
    policy = getattr(model, "policy", None)
    if policy is None or not hasattr(policy, "get_distribution"):
        return None

    import torch as th  # local: the estimator half of this module stays importable without it

    with th.no_grad():
        tensor, _ = policy.obs_to_tensor(obs)
        dist = policy.get_distribution(tensor)
        dist.apply_masking(th.as_tensor(np.asarray(mask, dtype=bool)).unsqueeze(0))
        return float(dist.entropy()[0])


def variance_components(grid) -> dict:
    """One-way random-effects decomposition by method of moments. Rows are event seeds,
    columns are decision repetitions within that seed; the value is a finishing position.

    The share is the intraclass correlation: the fraction of finishing-position variance
    that lives between event seeds rather than within one.
    """
    values = np.asarray(grid, dtype=float)
    n_seeds, n_reps = values.shape

    row_means = values.mean(axis=1)
    between_ms = n_reps * float(np.var(row_means, ddof=1)) if n_seeds > 1 else 0.0
    within_ms = float(np.mean(np.var(values, axis=1, ddof=1))) if n_reps > 1 else 0.0

    raw_between = (between_ms - within_ms) / n_reps
    between = max(0.0, raw_between)
    total = between + within_ms

    if total == 0.0:
        share, flag = float("nan"), "undefined_zero_variance"
    elif within_ms == 0.0:
        share, flag = 1.0, "degenerate_zero_within"
    else:
        share, flag = between / total, None

    return {
        "between": between,
        "within": within_ms,
        "share": share,
        # a negative variance estimate is sampling noise, not a finding; clipping is the
        # standard method-of-moments repair and the count is reported
        "clipped": bool(raw_between < 0.0),
        "flag": flag,
        "n_seeds": int(n_seeds),
        "n_reps": int(n_reps),
    }


def luck_share(grids_by_circuit, *, cfg, head_entropies=()) -> dict:
    """Per-circuit shares plus the headline mean, with an interval from resampling
    circuits. Circuits whose grid never varied carry no share and are excluded from the
    mean with their flag kept, so an undefined split cannot quietly read as zero luck.

    head_entropies is one StochasticSb3Policy.mean_head_entropy per rolled episode. Its
    mean is published with the share because a share measured under a near-collapsed head
    is a different claim from one measured under a hesitant one, and eval.yaml's m11
    gaming_note promises the reader that number.
    """
    per_circuit = {circuit: variance_components(grid)
                   for circuit, grid in grids_by_circuit.items()}
    shares = [block["share"] for block in per_circuit.values()
              if not np.isnan(block["share"])]

    interval = mean_interval(
        shares, level=cfg["bootstrap"]["ci_level"],
        resamples=cfg["m11"]["bootstrap_resamples"], seed=cfg["bootstrap"]["seed"],
    )
    probe = np.asarray(list(head_entropies), dtype=float)
    probe = probe[~np.isnan(probe)]
    return {
        "per_circuit": per_circuit,
        "mean_share": interval.mean,
        "ci_low": interval.low,
        "ci_high": interval.high,
        "n_circuits": len(per_circuit),
        "mean_head_entropy_nats": float(probe.mean()) if probe.size else float("nan"),
        "n_entropy_episodes": int(probe.size),
    }
