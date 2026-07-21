# F09 — explainability: the fidelity badge and the cross-check

The 5.8 pipeline run against the promoted headline triplet
`senna-ppo-6b6edb78d84e-C-00835584` (F08, seed 331, step 835,584), config fingerprint
`6b6edb78d84e`. Everything below was produced by one `make explain` and is
reproducible from the frozen constants in `configs/explain.yaml`. The artifacts live
in `models/explain/<model_version>/`, which is gitignored like the rest of `models/`,
so this document is the committed record. Figures are in `docs/explain/`; the
narrative reading of them is `notebooks/fit_surrogate.ipynb`.

**Why a surrogate at all.** The policy is an MLP. `shap.TreeExplainer` raises on it,
and `KernelExplainer` was priced by the master spec at roughly a billion forward
passes for the evaluation set — infeasible rather than slow (F-25). The v3 design
(A-04) distils the policy into gradient-boosted trees, runs exact TreeSHAP on the
distillate, and publishes how faithful the distillate is. The number below is that
publication.

## The badge

| Head | Top-1 agreement | Mean KL (nats) | Surrogate |
|---|---|---|---|
| pit (6 actions) | **0.9970** | 0.0141 | depth 6, 300 trees |
| mode (4 actions) | **0.9908** | 0.0077 | depth 6, 300 trees |

Gate: 0.90 per head (`fidelity.threshold`, sourced 5.8.2). Both heads cleared it on
the shallowest rung of the deepen ladder, so the deeper rungs were never fitted.

Measured on 39,878 held-out decisions from 200,009 (state, action-probability) pairs
across 3,320 evaluation rollouts. Two details decide whether that number means
anything:

- **The holdout splits at episode level, not state level.** Consecutive laps of one
  race are near-duplicates. A random state-level split would put a lap in training and
  its neighbour in holdout, and the badge would read high because the surrogate had
  effectively seen the answer. Whole races sit on one side or the other.
- **Agreement is scored after the mask is applied.** The surrogate is distilled
  against the policy's *unmasked* preferences, because the mask depends on per-circuit
  fitted compounds and a last-lap rule that no function of the 32-dim observation can
  recover. It is then scored the way a card consumes it: masked to the legal actions
  and renormalised. Scoring the raw distribution instead would understate a surrogate
  that is correct in use.

KL runs policy-first, `KL(policy || surrogate)`, over the legal actions. The policy
puts exact zeros on masked actions and those terms contribute nothing; the reverse
direction would divide by them.

## The cross-check

Everything above measures the surrogate. Whether the surrogate's *story* matches the
network's is a separate question, so `shap.GradientExplainer` attributed 500 sampled
decisions on the real MLP and the two attribution vectors were rank-correlated per
decision.

| Statistic | Value |
|---|---|
| Mean Spearman rho | **0.687** |
| Median | 0.699 |
| Interquartile range | 0.643 to 0.745 |
| Share positive | 100% of 500 |

Ranks rather than magnitudes, because the two explainers see different input scales
(raw observation against VecNormalize'd observation) while a card claims an *ordering*
of drivers, not their absolute size.

A word on how to read 0.687, since it is the number a viva will press on. It is a
moderate positive correlation, not a near-1.0, and that is the honest expected result
for a tree surrogate against a smooth network: the two agree on which handful of
features dominate and diverge on the ordering of the weak tail, where attributions are
close to zero and their ranks are mostly noise. Every one of the 500 sampled decisions
came back positive, which is the part that matters — no decision had the two views
disagreeing about what drove it. It is also the reason a card says *these inputs moved
the model most* and never *this is why the model decided*.

## Coverage

| | |
|---|---|
| Decision cards written | 14,460 |
| Evaluation races carded | 240 (24 circuits x 10 validation seeds) |
| Cards carrying a counterfactual flip line | 48.2% |
| Background states | 1,024 across 204 non-empty strata |

Cards are stored one JSONB per decision in `agent_decisions` (5.3.5), under one
`simulation_runs` row per race carrying `model_version`, `env_config_hash` and a
`purpose` discriminator. Re-running `make explain` delete-and-rewrites that set in one
transaction, so the table never accumulates duplicates.

Of the 14,460 decisions, 257 are pit calls (220 onto Soft, 13 Hard, 9 Medium, 8 Wet,
7 Intermediate) and the rest are stay-out. That ratio is what a lap-level decision
log should look like for one-to-three-stop races over roughly 57 laps.

### The background set

Attributions are marginal contributions *relative to a background distribution*, so
the composition is documented rather than assumed:

| Track status | States | Race phase | States |
|---|---|---|---|
| green | 364 | early | 340 |
| VSC | 330 | mid | 344 |
| SC | 330 | late | 340 |

Safety-car and VSC laps are rare in the logged pool, and a proportional draw would
have left almost none of them in the background — exactly the states the interesting
pit calls live in. Every non-empty stratum therefore gets an even share first, with
leftover capacity going to whichever stratum has the most room. The full 204-stratum
breakdown is `background_composition.json`.

### Flip-line coverage, and why it is not 100%

A flip probe sweeps one feature across its physical range against the true policy,
recomputing the action mask at every sweep point, and reports where the call changes.
Slightly under half of all cards carry such a line; the rest say plainly that no single
sweepable feature flips the call within its range.

That figure is a real limit, not a bug, and it is worth stating precisely. On 89.6% of
cards the single strongest driver is a one-hot — the compound fitted, the track status,
the override window — and there is no value between "Soft" and "Medium" to sweep
through. The probe ranks every dimension by attribution and sweeps the strongest
*sweepable* ones (up to `flip.max_sweeps`), which is what lifted coverage from 6.2% to
48.2% during this feature's build. The remainder are mostly mid-stint stay-out calls
that genuinely hold across the whole range of every continuous input, which is itself
an honest thing for a card to say.

Sample lines, with the physical translation the card carries:

    the call flips if soc_frac crossed 0.60 (about 2.4 MJ in the store)
    the call flips if behind_tyre_age_delta crossed -0.71 (about 29 laps fresher)
    the call flips if pit_count_norm crossed 0.29 (about 1 stop)

## What the mask reasons show

Every card carries the reason code for each option the mask removed, so an absent
option is explained rather than silent. Across the 14,460 cards:

| Reason | Count |
|---|---|
| `wet_requires_wet_track` | 13,583 |
| `inter_outside_damp_band` | 12,767 |
| `slick_above_wet_threshold` | 7,644 |
| `compound_unfitted_for_circuit` | 764 |

The last row is worth noting: that is the unfitted-compound guard added before F08's
headline runs (INDEX, 19 Jul), and it is a data limit rather than a sporting rule. It
fires on 764 decisions and the cards say so by name, which is the behaviour the
interpretability contract asks for — a constraint the agent faced because the circuit
has no degradation fit for that compound, not because the regulations forbade it.

## Reproducing this

    docker compose up postgres            # cards land in agent_decisions
    make explain                          # about an hour on a 10-core M-series Mac

`make explain PAIRS=3000 RACES=10 SKIP_PERSIST=1` smokes the wiring in a couple of
minutes; note that the cross-check needs at least `crosscheck.sample` carded decisions,
so a narrower run refuses rather than quietly measuring the integrity statistic on
less than the spec asks for. `--reuse-surrogate` rebuilds the cards from the frozen
boosters without repeating the distillation.

Two environment notes. `OMP_NUM_THREADS=1` is set by the Make target and by the module
itself: torch and xgboost each bundle their own OpenMP runtime, and on arm64 the two
in one process segfault once both do real work. And the run reads `models/headline/`,
so a retrain invalidates these numbers by construction — card generation reads the
version back out of the surrogate artifact and refuses to explain a checkpoint it was
not fitted to (E-15).
