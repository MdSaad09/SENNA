# F09 — Explainability: the surrogate, SHAP and the decision card

## What we built and why

The pit wall calls it on lap 28: box for mediums, attack on the out-lap. Someone asks
why. "The model said so" ends the conversation and ends your viva with it. What you
want to be able to say is: these five things about the state moved the call most, this
one pushed hardest, and here is the exact tyre age at which the same model would have
stayed out instead.

That is the artifact F09 builds, one per decision, called a decision card (5.8.3). It
carries the named state the agent saw, which options the mask allowed and why the rest
were closed, the five inputs that mattered most for each head, a counterfactual line
saying where the call flips, one sentence of plain English, and a footer stating how
much of this you should believe.

The footer is the interesting part, and it exists because the obvious plan was
impossible. The trained policy from F07 is a small neural network. The standard fast
SHAP tool, `shap.TreeExplainer`, only works on tree models and raises the moment you
hand it a network. The general-purpose fallback, `KernelExplainer`, needs thousands of
forward passes for every single decision explained, and the master spec worked out
v2's plan at roughly a billion forward passes for the eval set. Not slow. Not
feasible. That is audit finding F-25.

The fix (A-04) is to train a second, simpler model, a gradient-boosted tree, to imitate
the network. Trees are what TreeSHAP is exactly and cheaply computable on, so every
decision gets an exact attribution in milliseconds. The cost is that you are now
explaining a copy, and the copy is not perfect. So F09 measures how good the copy is
and prints that number on every card it ships, refuses to ship anything at all if the
number is too low, and separately checks a sample against the real network to confirm
the two agree about what matters. The approximation is stated out loud rather than
hidden. That is the whole feature, and it is what makes it defensible.

## New ideas in this feature

**What a SHAP value actually is, and why it needs a background (5.8.1).** The policy
turns the 32-dim state into a preference score (a logit) for each of the six pit
actions and four mode actions. A SHAP value for feature *i* is that feature's average
contribution to the chosen action's score, averaged over every order in which you
could add the features in. It comes from cooperative game theory: the features are
players, the score is the payout, Shapley's axioms say how to split the payout fairly.
Positive means the feature pushed toward the call; negative means the call happened
despite it.

The clause people skip is "contribution relative to what". A contribution is a
difference, and a difference needs a baseline. In SHAP that baseline is a background
set of states, and the attribution literally means "how much of the gap between the
score at this state and the average score over the background is attributable to
feature *i*". Change the background and you change every number. Saying "gap behind
contributed 0.22" without saying what you compared against is like saying a car is
three tenths quicker without saying than what. SENNA uses 1,024 background states and
writes their composition to disk as an artifact, because 5.8.2 requires the choice to
be documented.

**Surrogate distillation, and the fidelity gate (F-25, A-04).** Distillation means
fitting a simpler model to reproduce a complex model's outputs rather than the original
training labels. Here: log 200,000 (state, action-probability) pairs by rolling the
frozen policy, then fit one XGBoost multi-class model per action head against those
probabilities. Fidelity is how often the surrogate's top choice matches the policy's,
on states it never saw during fitting. The spec's bar is 90% per head, and in SENNA
that bar is `distill_or_refuse`: try progressively deeper surrogates, and if the last
one still misses, raise `FidelityGateError` and emit nothing. Mental model: a stand-in
who mimics the driver. Useful for showing the world what the driver does, but only if
you keep publishing how often the stand-in gets it right, and you pull the stand-in
entirely once the agreement drops. The viva answer: **TreeSHAP is exact and cheap but
only defined on trees, and KernelExplainer on the real network was priced at about a
billion forward passes (F-25), so A-04 distils the policy into a tree surrogate and
reports the top-1 agreement on held-out states next to every explanation. The
approximation is a published number gated at 0.90 in code, so an explanation can never
ship quietly attached to a bad imitation.**

**Weighted row expansion, or how to fit soft targets with a stock objective.** XGBoost's
`multi:softprob` wants one integer label per row. We do not have a label, we have a
probability vector: the policy is 70% stay out, 30% pit for medium. The textbook fix is
a custom objective where you write the gradients and hessians by hand. The trick used
here is smaller and does the same job. Emit one row per action that has real mass:

    state x, probs [0.7, 0.3, 0, 0, 0, 0]
      ->  (x, label 0, weight 0.7)
          (x, label 1, weight 0.3)

Weighted cross-entropy over the expanded rows is `0.7·(−log p₀) + 0.3·(−log p₁)`, which
is exactly the soft-target cross-entropy for that state, term by term. Stock objective,
no custom gradients, and TreeSHAP works on the result without caveats.

**The gradient cross-check, and why ranks (A-04).** `shap.GradientExplainer` does work
on a neural network, just too slowly to run on every decision. So it runs on a sample
of 500, and the reported statistic is the Spearman rank correlation between the
surrogate's attributions and the network's, per decision. Spearman correlates the
*order* of the features rather than their values. That is deliberate: the two
explainers use different models, different backgrounds and different input scalings, so
their raw magnitudes are not on a common ruler, but "which features mattered most" is
comparable and is the claim the card actually makes. The viva answer: **the surrogate
could be faithful in its choices and still attribute for different reasons, so
GradientExplainer attributes the true network on a 500-decision sample and the mean
Spearman rho between the two is reported as an integrity statistic; ranks rather than
magnitudes because a tree margin and a network logit are not on a common scale, while
the ordering of the drivers is exactly what the card claims.**

**Counterfactual flip probes (5.8.2).** The most persuasive line on a card is the one
that names the edge. Take the recorded state, sweep one feature across its physical
range with everything else frozen, ask the real policy at each point, and record where
its choice changes. It is model-faithful because it queries the network itself, and it
is cheap because it is one feature at a time. It is also easy to get subtly wrong in
two ways, both of which are handled in `flip.py` below.

## The code, guided

Reading order follows a run: name the features, log what the policy did, fit and gate
the surrogate, attribute, cross-check, probe, card, persist.

### features.py — the names, and the units

`FEATURE_NAMES` is a 32-tuple mirroring `observation.encode` exactly. SHAP returns a
vector of 32 numbers; without this table a card would say "feature 19 contributed
0.19". A perturbation test (`test_perturbation_maps_to_named_dim`) changes one physical
quantity in a built state and asserts only the named dimension moved, so the mapping
cannot silently drift when the observation changes.

`SWEEPABLE` is the table of dims a flip probe is allowed to touch, with their encoded
bounds. One-hots and booleans are excluded on purpose: "what if `compound_is_soft` were
0.4" is not a race state, and reporting it as a counterfactual would be fiction. The
tri-state tyre-temperature dim lists its three legal values `(0.0, 0.5, 1.0)` instead
of a range, which is why `flip_lines_for` in `run.py` branches on `len(bounds) == 3`.

`physical_note` is the "i.e. about 17 laps" clause of 5.8.2, undoing the observation's
normalisation so a card speaks race units. Two lines earn attention:

```python
    if dim in (19, 21):
        # a signed delta: dropping the sign would report a rival 17 laps fresher as
        # 17 laps older, inverting the reason for the call
        laps = value * age_norm
        return f"about {abs(laps):.0f} laps {'older' if laps >= 0 else 'fresher'}"
```

Dims 19 and 21 are signed tyre-age deltas against the cars ahead and behind, encoded on
[-1, 1]. Formatting `abs(laps)` without the word swap would turn a fresher rival into an
older one and invert the entire reason for the pit call. The function returns an empty
string for dims that are genuinely dimensionless (grip, position fraction, wetness),
because inventing a unit would advertise precision the encoding does not carry.

### dataset.py — recording what the policy preferred

`DecisionLogger` wraps F07's `Sb3Policy` behind the same `StrategyPolicy` protocol the
F06 rollout harness expects, and records one `DecisionRecord` per `act()` call. The
core is six lines:

```python
        action = np.asarray(self._inner.act(obs, info, mask))
        mask_flat = np.asarray(mask, dtype=bool)

        policy = self._inner.model.policy
        with th.no_grad():
            tensor, _ = policy.obs_to_tensor(self._inner.normalize_obs(obs))
            dist = policy.get_distribution(tensor)
            pit_unmasked, mode_unmasked = _head_probs(dist)
            dist.apply_masking(th.as_tensor(mask_flat).unsqueeze(0))
            pit_masked, mode_masked = _head_probs(dist)
```

The real policy acts first, so the record is of the decision that actually happened
rather than a re-query that might differ. `no_grad` because we are reading the network,
not training it, and this runs 200,000 times. `normalize_obs` applies the frozen
VecNormalize statistics from the triplet (F07), so the network sees exactly the input it
acted on. `get_distribution` with no masks gives the unmasked head distributions, then
`apply_masking` mutates the same object and we read it again. Two snapshots of one
forward pass.

Why keep both, and why is the *unmasked* pair the distillation target? This is the
subtlety most worth slowing down for. The surrogate's only input is the 32-dim
observation. The mask is not a function of that observation. It reads which slick
compounds have a degradation fit at this circuit (F08's `UNFITTED_COMPOUND` guard: SOFT
is masked at Suzuka and legal at Bahrain) and the exact last-lap forced-pit trigger from
F-20. Two states with byte-identical observations at two circuits can have different
masks. If you distilled the masked probabilities, you would be asking a function of the
observation to reproduce something that is not a function of the observation. The target
is multi-valued, the tree can only average across the disagreement, and fidelity is
silently capped below whatever the mask disagreement rate happens to be. You would never
see the cause, only a badge that refused to climb.

The unmasked distribution *is* a pure function of the observation, and it is also
precisely what 5.8.1 defines a SHAP value as explaining: the preference score. So the
surrogate learns preference, and the mask is applied afterwards, at scoring time and at
card time. Worth holding on to for the viva: the mask is recoverable from the
observation *plus* the circuit's constants, which is why `run.py` can rebuild it during
a flip sweep, and is not recoverable from the observation alone, which is why the
surrogate cannot learn it.

`derived_seeds` draws the distillation episode seeds from a frozen base with a floor:

```python
    rng = np.random.default_rng(base)
```

with `floor = 1_000_000` from config. Every seed in `configs/seeds.yaml` is six digits,
so a seven-digit floor makes these rollouts provably disjoint from the train, validation
and reserved F14 test banks by construction. No exclusion list to maintain, nothing to
forget on the day someone adds a bank (E-06). The loop draws in batches and dedupes so
the count is exact.

`split_by_episode` is the fidelity holdout, and it splits at episode granularity:

```python
    episodes = sorted({(r.circuit, r.seed) for r in records})
    ...
    held = {episodes[i] for i in order[:n_holdout]}
```

Lap 30 and lap 31 of the same race differ in maybe three dimensions. A random
state-level split would drop near-copies of training rows into the holdout, and the
fidelity badge would be measuring memorisation. Episode-level, and the whole race goes
one way or the other. This is F03's leakage discipline (E-14) applied to a number that
gets printed on every card we ship. The function raises rather than silently taking
every episode if the fraction is set too high.

### surrogate.py — the trick, the yardstick, and the gate

`expand_soft_labels` is the row-expansion trick from above, in three lines:

```python
    keep = probs >= weight_floor
    state_idx, labels = np.nonzero(keep)
    return X[state_idx], labels.astype(np.int64), probs[keep].astype(np.float64)
```

`keep` is an (n_states, n_actions) boolean of cells worth a row; the 0.01 floor drops
crumbs, which add trees without adding fidelity. `np.nonzero` on a 2-D boolean returns
two parallel arrays, row indices and column indices, which here mean exactly "which
state" and "which action label". `X[state_idx]` repeats each state row once per kept
action. `probs[keep]` walks the same cells in the same C order, so weights line up with
labels without any explicit zip.

`masked_top1_and_kl` measures fidelity the way the card will consume the surrogate,
which is the point of the function:

```python
    surrogate = np.where(masks, np.asarray(surrogate_probs, dtype=np.float64), 0.0)
    row_mass = surrogate.sum(axis=1, keepdims=True)
    if np.any(row_mass == 0.0):
        raise ValueError("a surrogate row has no mass on any legal action")
    surrogate /= row_mass
```

Zero out the illegal actions, then renormalise. A card never displays an illegal action,
so the badge must not be earned on one, and a surrogate that puts most of its mass on a
masked action while getting the legal argmax right is worse than the raw number would
suggest. The raise is not defensive noise: renormalising a row of zeros would invent a
distribution out of nothing.

```python
    top1 = float(np.mean(surrogate.argmax(axis=1) == policy.argmax(axis=1)))

    support = policy > 0.0
    ratios = np.divide(policy, surrogate, out=np.ones_like(policy), where=support)
    mean_kl = float(np.mean(np.sum(policy * np.log(ratios), axis=1, where=support)))
```

Top-1 is the gate: same call or not. KL is the second number, and it exists because
top-1 is binary and cannot tell 0.51-versus-0.49 from 0.99-versus-0.01. Two surrogates
with the same badge and very different KLs are not equally trustworthy. The direction is
KL(policy ‖ surrogate), policy first, because the policy's masked distribution holds
exact zeros on illegal actions and those terms contribute nothing to a
policy-weighted sum; the reverse direction would divide by them. `out=np.ones_like`
makes the skipped cells log(1) = 0 rather than a warning.

`distill_or_refuse` is the gate itself:

```python
    for rung in ladder:
        surrogate, top1, mean_kl = fit_rung(rung)
        if top1 >= threshold:
            return surrogate, top1, mean_kl
        best = max(best, top1)
    raise FidelityGateError(...)
```

The ladder walks shallow to deep (depth 6/300 trees, then 8/600, then 10/1200) because
5.8.2 says to deepen the surrogate before shipping explanations, and because a shallower
surrogate is an easier one to defend. First rung that clears 0.90 wins; miss the last
and the run dies with the best achieved agreement in the message. Nothing partial ships.
`test_pipeline_refuses_cards_below_fidelity` and `test_deepen_ladder_retries_before_refusing`
pin both halves.

One line in `fit_head` is easy to skip and load-bearing:

```python
            "base_score": 0.5,
```

xgboost 3.x otherwise fits its own intercept, which TreeSHAP would have to guess, and
the additivity property (attributions plus expected value equals the model's margin)
would drift. `test_treeshap_additivity` is a hypothesis property test that holds the
pair together to 1e-4 across randomly drawn states. `nthread: 1` is
the arm64 landmine: torch and xgboost each bundle their own OpenMP runtime and two in
one process segfault. `OMP_NUM_THREADS=1`, set at the top of `run.py` before either
library loads, is the cure; the models are small enough that it costs nothing.

### attributions.py and crosscheck.py — the two explainers, kept apart

F-25 is made structural here rather than promised in prose. `head_explainer` accepts a
booster and nothing else:

```python
    return shap.TreeExplainer(booster, data=np.asarray(background),
                              feature_perturbation="interventional")
```

The only object `shap.TreeExplainer` is ever handed in this repo is an XGBoost Booster.
`data=background` with interventional perturbation is what makes the attribution mean
"against these 1,024 documented states". The explainer is built once per head and reused
across every card, because preparing that background is the expensive part and the
booster does not change.

`top_drivers` sorts by absolute attribution and keeps the sign:

```python
    order = np.argsort(-np.abs(shap_row), kind="stable")[:k]
```

`kind="stable"` because zero-attribution ties are common across 32 features and
quicksort would order them differently between runs. A card that reshuffles its drivers
on a rerun invites exactly the "is this thing deterministic" doubt the layer exists to
remove.

`crosscheck.py` is the only place anything touches the real network. `_HeadLogits` is a
thin torch module because GradientExplainer needs something mapping an input tensor to
an output tensor, and SB3's policy returns actions:

```python
        def forward(self, obs):
            latent = self.policy.mlp_extractor.forward_actor(
                self.policy.pi_features_extractor(obs)
            )
            return self.policy.action_net(latent)[:, head_slice]
```

Features extractor, actor trunk, action head, then slice out this head's logits (pit is
0:6, mode is 6:10 of the ten concatenated outputs). Unmasked logits, matching the
surrogate's target. Inputs are normalised the same way the policy normalises them. The
shape guard below it raises if the returned array is not (n, 32, actions), because a
shap upgrade that changed the layout would otherwise leave the pipeline rank-correlating
noise and reporting it as an integrity statistic.

`rank_correlation` is one line of scipy over the 32 features, with ties at their average
rank; `run_crosscheck` in `run.py` calls it per decision on the absolute attributions
for the action actually chosen, and reports the mean.

### flip.py — the counterfactual, and its two traps

Thirty-two lines, and both interesting decisions are in them.

```python
    recorded = policy_fn(obs, mask_fn(obs))
    swept = obs.copy()

    def differs(i: int) -> bool:
        swept[dim] = grid[i]
        return policy_fn(swept, mask_fn(swept)) != recorded
```

Trap one: `mask_fn(swept)`, not `mask_fn(obs)`. The mask is rebuilt at every sweep
point. Sweeping wetness upward crosses the compound-legality thresholds; sweeping SOC
downward crosses the attack floor. With the recorded mask held fixed, the sweep would
happily report "the call flips to pit for wets at wetness 0.51" at a wetness where the
env would have masked wets off entirely. That is a card making a claim about a state
the agent could never have been in. `test_sweep_recomputes_mask` builds an over-eager
policy that wants wets from 0.5 and a mask that permits them from 0.7, and asserts the
reported flip is 0.70.

```python
    start = int(np.clip(np.searchsorted(grid, float(obs[dim])), 0, len(grid) - 1))
    for offset in range(len(grid)):
        for i in dict.fromkeys((start - offset, start + offset)):  # nearer side first
            if 0 <= i < len(grid) and differs(i):
                return float(grid[i])
    return None
```

Trap two, and this one was a live bug caught in review. `searchsorted` finds where the
recorded value sits on the grid, and the loop then walks outward from it, checking the
lower side first at each distance. The original scanned from index 0 upward. For a
decision whose feature already sits high in its range, that returns the bottom of the
range: the policy does behave differently down there, but it is not the nearest
counterfactual, and the card would read "the call flips if tyre_age_norm crossed 0.00
(about 0 laps old)". A true sentence about the sweep and a false statement about the
decision. `test_flip_reports_the_nearest_crossing` puts a recorded tyre age at 0.8 with
the flip at 0.42 and demands 0.42, not 0.00. `dict.fromkeys` deduplicates the offset-0
case where both candidates are the same index while preserving the lower-first order
that a set would throw away.

Returning `None` is a real answer, and `run.py` renders it as "no single sweepable
feature flips this call within its physical range" rather than dropping the field.

### background.py — 1,024 states, and why rare ones get an even share

Strata are (circuit, race phase, track status); phase comes from lap fraction against
the configured 0.25/0.75 bands. The allocation is two steps:

```python
    counts = {key: min(size // len(keys), len(strata[key])) for key in keys}
    while sum(counts.values()) < size:
        key = max(keys, key=lambda k: (len(strata[k]) - counts[k], k))
        counts[key] += 1
```

Every non-empty stratum gets an even share first, capped by what it actually holds. The
leftover slots then go one at a time to whichever stratum has the most states still
spare, ties broken on the key so the result is deterministic. The draw within each
stratum is `rng.choice(..., replace=False)` in sorted key order, so the same seed gives
the same 1,024 states.

Even shares rather than proportional is the design choice worth defending. Safety-car
and VSC laps are a few percent of all laps. A proportional draw would put a handful of
them in the background, and since attributions are contributions measured against the
background, every safety-car pit call would be explained relative to an almost entirely
green baseline. Those are the calls the whole project is about. The composition dict is
returned alongside the states and written to `background_composition.json`, because
5.8.2 requires the choice to be documented rather than assumed.

### cards.py — the artifact, and the refusal

`build_card` assembles the 5.8.3 fields into the JSON that becomes one `agent_decisions`
JSONB row. Block-level for most of it: named state, masks with their reason codes
straight from the env info dict (so a card explains why an option was closed, including
F08's `compound_unfitted_for_circuit` data limit), the action, masked probabilities,
top-5 drivers per head, flip lines, plain-language line, honesty footer. Everything is
cast to Python floats and bools because JSONB will not take numpy types, and
`zip(FEATURE_NAMES, record.obs, strict=True)` raises on a length mismatch instead of
silently truncating the state.

Two things are not boilerplate. The first is the first statement in the function:

```python
    if surrogate_version != model_version:
        raise VersionMismatchError(
            f"surrogate fitted to {surrogate_version} cannot explain "
            f"{model_version} — re-run make explain against the current triplet (E-15)"
        )
```

Never explain a ghost. A surrogate fitted to one checkpoint says nothing reliable about
another, so retraining invalidates every old explanation. E-15 in F10 is the same
pairing rule for the served model.

The second is `_plain_language`, which is a fixed template and deliberately not a
generated sentence:

```python
    if top_value >= 0:
        reason = f"{driver} was the strongest push toward this call"
    else:
        reason = f"the call held despite {driver} pushing against it"
```

The branch matters: the largest-magnitude driver for the chosen action can be negative,
meaning the model picked this call in spite of that feature. A template that assumed
"strongest reason for" would state the opposite of the attribution. Nothing here
generates text, because the card must never say more than the attribution supports.

### persist.py and run.py — sequencing and idempotency

`persist.py` is F01's delete-and-reload idempotency applied to cards: inside one
transaction, delete every `SimulationRun` and `AgentDecision` for this
(model_version, purpose) pair, then insert fresh. Re-running `make explain` lands on the
same rows rather than doubling them. The `purpose: "F09-eval-cards"` discriminator
exists because F10's served runs will share these tables and must not be swept up by
F09's delete.

`run.py` sequences everything, and one ordering decision is worth the whole section:

```python
    write_surrogate_artifacts(dest, heads=heads, background=background, ...)
    # read the version back out of the artifact the cards are about to be built
    # from: a stale models/explain/ is then caught by build_card, not trusted (E-15)
    _, surrogate_version = load_surrogates(dest)
```

The surrogate artifacts are written before a single card exists, and the version the
cards are checked against is then read back off the manifest on disk. If the version had
simply been passed along in a variable, `build_card`'s guard would be comparing a
variable to itself, a check that can never fire. Reading it back makes the guard real: a
stale `models/explain/` directory, a half-written artifact or a hand-edited manifest all
get caught. `write_surrogate_artifacts` also unlinks the manifest first and writes it
last, so a run that dies mid-write leaves no manifest whose hashes describe boosters
that are gone. Same instinct as F07's atomic triplet.

The other function worth reading is `pit_mask_fn`, which is the flip probe's mask
rebuilder and the concrete proof of the earlier claim about obs-plus-scenario:

```python
        return build_mask(
            pit_open=bool(obs[26] > 0.5),
            weather=int(np.argmax(obs[27:30])),
            wetness=float(obs[30]),
            soc_mj=float(obs[14]) * scenario.usable_soc_mj,
            lap=int(round(float(obs[0]) * scenario.total_laps)),
            ...
            fitted_slick_actions=fitted,
        ).pit
```

Every input to F05's `build_mask` is either decoded from the swept observation or a
constant of the circuit's scenario. `test_reconstruction_matches_the_env_mask` asserts
this reproduces the env's own mask, so the probe cannot drift away from the real rules.
Note what has to come from the scenario rather than the obs: `usable_soc_mj`,
`total_laps`, and `fitted_slick_actions`. That is the same list that makes the mask
unlearnable from the observation alone.

`configs/explain.yaml` holds every constant with its provenance, sourced or stylised in
the usual F00 style. The 0.90 threshold, 200k pairs, 1,024 background states and the
500-decision cross-check sample are all sourced to 5.8; the ladder rungs, phase bands,
sweep resolution, seed base and seed floor are stylised choices with their reasoning
inline. The results of the production run go to `docs/results/F09-explainability.md`,
because `models/` is gitignored and the badge has to survive in the repo.

## How it connects

```
 models/headline/ (F07 triplet, F08-selected)
      │  load_triplet + frozen VecNormalize statistics
      ▼
 dataset.DecisionLogger ── rollouts on derived seeds (>= 1e6, disjoint: E-06)
      │  records: obs · mask+reasons · unmasked probs · masked probs
      ├─────────────► split_by_episode (E-14 discipline)
      │                    │ train                        │ holdout
      ▼                    ▼                              ▼
 background.py        surrogate.fit_head              masked_top1_and_kl
 1,024 stratified     (row expansion, ladder)              │
      │                    │                               ▼
      │                    └──────────────► distill_or_refuse  ── < 0.90 ─► STOP
      ▼                                          │ passes
 attributions.TreeSHAP  ◄──── background ────────┘  models/explain/<version>/
      │                                                (boosters, manifest, fidelity)
      ├─ crosscheck.GradientExplainer ─► Spearman rho   [the only path to the MLP]
      ├─ flip.find_flip ─► the true policy, mask rebuilt per sweep point
      ▼
 cards.build_card ── E-15 version check ─► persist ─► agent_decisions (JSONB, 5.3.5)
                                                          │
                                                          ▼
                                        F10 serves cards · F13 draws them · F14 quotes
```

## Try it yourself

All commands from the repo root. `make` recipes call bare `python`, so run them under
`uv run` or with the venv active.

1. **Run the suite.** `.venv/bin/python -m pytest tests/explain -q`. Twenty-three tests in
   about four seconds, two of them skipped unless `DATABASE_URL` is set (the persist
   pair needs a live Postgres, the `tests/data` pattern). Then open `tests/explain/test_flip.py` and read the three tests in
   order. You will know you have it when you can say, without looking at `flip.py`, what
   each of the two traps is and which test guards it.

2. **Predict a config change, then check it.** In `configs/explain.yaml`, set
   `flip.sweep_points` from 64 to 8. Before running anything, write down what you expect
   to happen to the reported flip values and to the number of cards that say "no single
   sweepable feature flips this call". Then run the smoke in exercise 4 and compare. You
   will know it worked when the flip values land on a visibly coarser grid and more
   cards report no flip, because a coarse grid can step straight over a narrow crossing.
   Revert.

3. **Break the outward sweep.** In `senna/explain/flip.py`, replace the `start = ...`
   line with `start = 0`, then run
   `.venv/bin/python -m pytest tests/explain/test_flip.py -q`. You will know it worked
   when `test_flip_reports_the_nearest_crossing` fails with 0.0 against an expected 0.42.
   That is the exact bug review caught, and the failure message is the false card line it
   would have produced. Revert.

4. **Run the pipeline small.**
   `uv run make explain PAIRS=3000 RACES=10 SKIP_PERSIST=1` — a few minutes. `PAIRS`
   overrides `distill.pairs`, `RACES` cards only the first N validation races, and
   `SKIP_PERSIST` skips the database write. Then read
   `models/explain/<model_version>/background_composition.json` and
   `fidelity.json`. Two things to notice: the composition shows which strata were thin
   enough to be capped below their even share, and the fidelity payload records the rung
   that won as well as the badge. Two honest failure modes on a sample this small, both
   of which are the feature working: `FidelityGateError` if 3,000 pairs is not enough to
   imitate the policy, and the cross-check refusing if ten races yield fewer than the
   500 decisions `crosscheck.sample` demands (raise `RACES`).

5. **Read a card out of Postgres.** With the stack up (`docker compose up -d postgres`)
   and a full `make explain` behind you:

   ```
   docker compose exec postgres psql -U senna -d senna -c \
     "select jsonb_pretty(decision) from agent_decisions order by id limit 1;"
   ```

   Find the honesty footer, the flip lines and the masks block. You will know you have
   read it properly when you can point at the reason code for a closed pit option and
   say whether it was a sporting rule or a data limit (F08's distinction), and when you
   can explain why the `probs` block holds masked probabilities while the surrogate was
   fitted to unmasked ones. Then run `make explain` a second time and confirm the row
   count is unchanged.

## Check yourself

1. Why can `shap.TreeExplainer` not be pointed at the trained policy, and why was
   `KernelExplainer` not simply the slower answer?

2. The surrogate is fitted to the policy's unmasked action probabilities, not the masked
   ones the agent actually sampled from. Explain why, and what would go wrong with the
   masked targets.

3. Fidelity is measured on a holdout split at episode level rather than at state level.
   What does the state-level split get wrong, and roughly which direction does the error
   go?

4. Defend this design choice: the whole explanation layer explains a surrogate rather
   than the model that made the decision. What stops that from being a bait and switch?

5. A card says "the call flips if `tyre_age_norm` crossed 0.42 (about 17 laps old)".
   Name the two mistakes the sweep could have made in producing that line, and what the
   card would have said in each case.

---

### Answers

1. TreeSHAP's exact algorithm is defined over tree ensembles, walking the tree
   structure, so `TreeExplainer` raises immediately on a multilayer perceptron. It is
   not a limitation you can wait out. `KernelExplainer` does work on any model, but it
   approximates Shapley values by sampling coalitions, which means thousands of forward
   passes per explained decision; the master spec priced v2's plan at roughly a billion
   forward passes over the eval set (F-25). That is a different category from slow, and
   it is why A-04 replaces the approach rather than tuning it.

2. The surrogate's only input is the 32-dim observation, and the mask is not a function
   of the observation: it depends on which slick compounds have a degradation fit at
   this circuit and on the last-lap forced-pit trigger (F-20), neither of which is
   encoded. Identical observations at two circuits can carry different masks, so masked
   probabilities are a multi-valued target. The tree would average across the conflict,
   fidelity would be capped below the mask disagreement rate, and nothing in the output
   would tell you why. The unmasked distribution is a genuine function of the
   observation and is exactly what 5.8.1 says a SHAP value explains, so the surrogate
   learns the preference and the mask is applied afterwards, when scoring fidelity and
   when building a card.

3. Consecutive laps of one race are near-duplicates, differing in a handful of
   dimensions. A random state-level split therefore puts near-copies of training rows
   into the holdout, and the surrogate scores well by recognising states it has
   effectively already seen. The error is one-directional: it inflates the badge. Since
   the badge is printed on every card and gates the whole pipeline at 0.90, inflating it
   is the one direction we cannot tolerate, which is why the split is at episode level
   (E-14's discipline applied to fidelity).

4. It would be a bait and switch if the substitution were hidden. The three things that
   stop it: the top-1 agreement between surrogate and policy is measured on held-out
   episodes and printed on every card in the honesty footer; the pipeline refuses to
   emit anything at all below 0.90, so no card can exist without a badge that clears the
   bar; and the flip lines are queried against the real network, not the surrogate, so
   the most concrete claim on the card is model-faithful. On top of that,
   GradientExplainer attributes the true network on a sample and the rank correlation
   with the surrogate's attributions is reported, so agreement in the *reasoning* is
   measured too, not just agreement in the choice. The alternative was not a better
   explanation, it was no explanation at all (F-25).

5. First, it could have held the recorded mask fixed across the sweep, in which case it
   might report a flip onto an action the env would have forbidden at that swept value:
   the classic case is sweeping wetness and claiming the model would have taken wets at
   a wetness where the wet tyre is still masked off. `find_flip` rebuilds the mask at
   every point. Second, it could have scanned from the bottom of the range instead of
   outward from the recorded value, which for a decision already sitting high in the
   range returns the range floor: the card would have read "flips if `tyre_age_norm`
   crossed 0.00 (about 0 laps old)", a true statement about the sweep and a false one
   about the decision. The outward walk returns the nearest crossing, which is the only
   one that is a counterfactual about this decision.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| SHAP values and the background set (5.8.1) | F09 | A feature's average marginal contribution to the chosen action's logit under the Shapley axioms, always measured *against* a stated background distribution — SENNA's is 1,024 stratified states, documented as an artifact because the attributions depend on it. |
| Surrogate distillation and the fidelity gate (F-25, A-04) | F09 | TreeSHAP only works on trees and KernelExplainer on the MLP was priced at ~1e9 forward passes, so a gradient-boosted tree is fitted to imitate the policy; top-1 agreement on held-out episodes is printed on every card and `FidelityGateError` refuses to ship below 0.90. |
| Weighted row expansion for soft targets | F09 | Fitting probability targets with a stock `multi:softprob` objective by emitting one row per action with weight equal to its target probability — weighted cross-entropy over the expansion equals the soft-target cross-entropy, no custom gradients. |
| Masked fidelity (measured as the card consumes it) | F09 | Fidelity scored after applying the recorded mask to the surrogate's distribution and renormalising, with mean KL(policy ‖ surrogate) reported alongside top-1 because a binary agreement rate cannot distinguish 0.51-vs-0.49 from 0.99-vs-0.01. |
| Counterfactual flip probe (5.8.2) | F09 | One feature swept across its physical range against the true policy with the mask rebuilt at every point, walking outward from the recorded value so the reported crossing is the nearest one rather than the range floor. |
| Rank-correlation cross-check (A-04) | F09 | GradientExplainer attributions on the real network for a 500-decision sample, Spearman-correlated with the surrogate's TreeSHAP; ranks rather than magnitudes because tree margins and network logits are not on a common scale. |
| Episode-level holdout for a reported metric (E-14 applied) | F09 | Splitting the fidelity holdout by whole race rather than by state, because consecutive laps are near-duplicates and a state-level split leaks them across the boundary and inflates the badge in the one direction that matters. |
