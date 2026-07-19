# F09 — Explainability: surrogate, SHAP, decision cards — plan

Approved by Saad, 20 Jul 2026. Feature spec: docs/spec/features/F09-explainability.md.
Spec anchors: 5.8 (all), F-25, A-03, A-04, 5.3.5.

## Context

F08 promoted the frozen headline checkpoint (`senna-ppo-6b6edb78d84e-C-00835584`,
models/headline/) — the model F09 explains and F10 serves. The master spec's F-25 killed
v2's explainability plan (TreeExplainer on an MLP raises; KernelExplainer needs on the
order of a billion forward passes); the v3 fix (5.8, A-03, A-04) is a two-path design:
distill the policy into XGBoost surrogates with a reported fidelity number, run exact
TreeSHAP everywhere cheaply, cross-check on the true network with GradientExplainer, and
ship every decision as a recruiter-readable card with an honesty footer.

The groundwork already exists: the 32-dim named observation (senna/env/observation.py),
per-head masks with reason codes (senna/env/masks.py), the env info dict exposing
mask+reasons per step (senna/env/race_env.py), the triplet loader
(senna/train/checkpoints.py), the exact eval recipe (`score_triplet`,
senna/train/selection.py), frozen seed banks with the F14 test bank code-guarded
(senna/train/seeds.py), and the `agent_decisions` / `simulation_runs` Postgres tables
from F01 in exactly the 5.3.5 shape (senna/data/schema.py). `shap` (0.51.0) and
`xgboost` (3.2.0 — the `>=2.0` pin resolved to 3.x) are already pinned in
requirements.in (5.9.1) and installed.

Every library-level assumption below was verified against the installed venv before
planning: `policy.get_distribution(obs, action_masks=None)` returns the unmasked
per-head distributions (masking is applied only when masks are passed; `action_net`
emits 10 concatenated logits split [6, 4]); `shap.TreeExplainer` on a soft-target
booster returns `(n, 32, n_classes)` attributions whose sum plus `expected_value`
matches `predict(output_margin=True)` to ~1e-6 (set `base_score` explicitly);
`shap.GradientExplainer` on a torch head module returns the same `(n, 32, n_outputs)`
layout, so the rank-correlation pairing is direct; `VecNormalize.normalize_obs`
handles batches.

One environment landmine, found empirically: on this Mac (arm64), torch and xgboost
loaded in one process carry duplicate OpenMP runtimes and segfault when both do real
work; import order does not reliably cure it, `KMP_DUPLICATE_LIB_OK` does not either —
`OMP_NUM_THREADS=1` does, verified across the full interleaved pipeline. The models
are tiny, so single-threaded OpenMP costs nothing that matters.

## Objective & spec anchors

Every decision of the headline model explained honestly, per spec 5.8 (all):

- **F-25** — TreeSHAP only ever on the tree surrogate; the true MLP is touched only by
  GradientExplainer. Structural in code (only an xgboost Booster is ever handed to
  `shap.TreeExplainer`); the auditor enforces it.
- **A-04** — surrogate distillation with reported fidelity: top-1 agreement >= 90% per
  action head on held-out states, mean KL also reported; 500-decision gradient
  cross-check with attribution rank correlation as the integrity statistic.
- **A-03** — decision cards: top-5 SHAP drivers + counterfactual flip point per
  decision, plain-language line, honesty footer carrying the fidelity badge.
- **5.8.1** — the SHAP value explains the policy's *preference score* (logit) for the
  chosen action; the write-up says it is not a causal claim. This is why the surrogate
  distils the **unmasked** head distributions: they are a pure function of the 32-dim
  obs, exactly the "preference" 5.8.1 defines. The mask is not obs-recoverable (it
  reads per-circuit `fitted_slick_actions` and the exact last-lap trigger), so masked
  probs as targets would be multi-valued across circuits and silently cap fidelity.
- **5.8.2** — 200k (state, action-probability) pairs from evaluation rollouts; 1,024
  stratified background states, documented; counterfactual flip probes sweeping one
  feature across its physical range.
- **5.3.5** — one JSONB per decision in `agent_decisions` (state, masks with reasons,
  action, probs, shap top-k); `simulation_runs` carries model_version +
  env_config_hash. Both tables exist since F01 — no schema work.
- **E-15 pairing** (the F09 note: "never explain a ghost") — every artifact keys on
  model_version; a surrogate fitted to one checkpoint refuses to explain another.

## Design

**Data.** Roll the frozen triplet (deterministic head, `Sb3Policy` via `load_triplet` —
the `score_triplet` recipe) on the stochastic train-band env across the 24
validation-bank circuits until >= 200k per-lap pairs exist. The 240 validation races
yield only ~14k decisions, so distillation data comes from additional rollouts whose
episode seeds are derived from a frozen base in configs/explain.yaml and floored at
1,000,000 — every frozen bank seed is six digits, so disjointness from the train,
validation and reserved F14 test banks holds by construction (and
`load_reserved_test_bank` refuses non-F14 consumers anyway). Each logged pair: raw
32-dim obs, flat mask + reason codes, unmasked AND masked per-head probabilities (via
the policy's `get_distribution`), plus circuit/lap/track-status context. Post-hoc
surrogate fitting on fresh seeds is not policy tuning — no E-06 contamination.

**Surrogates.** One XGBoost multi-class model per head (pit 6-class, mode 4-class)
distilled on the policy's unmasked probabilities using weighted hard-label row
expansion: each state appears once per action with weight = target probability (rows
below a small floor dropped), stock `multi:softprob` — this minimises the soft-target
cross-entropy with no custom objective. (A custom soft-target objective was verified
working against xgboost 3.2 + TreeExplainer and stays in reserve if the ladder
stalls.) Fidelity is measured **as the surrogate will be used**: apply the recorded
mask to the surrogate's distribution, renormalise, then top-1 agreement and mean
KL(policy ‖ surrogate) over legal actions, per head, on a held-out split made at
**episode** level (consecutive laps are near-duplicates; a state-level split would
leak them into holdout and inflate the badge). A configured "deepen ladder" retries
deeper models until the 0.90 gate passes; below the gate the pipeline refuses to emit
anything — the gate is code, not intention.

**Explanations.** Exact TreeSHAP on the surrogate for every decision of the 240
validation-bank races (~14k cards); additivity asserted on samples (attributions +
expected value == the class margin). Background set: 1,024 states stratified circuit ×
race phase (early/mid/late on lap fraction) × track status (green/VSC/SC) from the
distillation pool; empty-stratum shortfall redistributed proportionally; the
composition is written to a JSON artifact because attributions depend on it.

**Cross-check.** `shap.GradientExplainer` on the true torch network (a thin wrapper
module: normalized obs -> the head's unmasked logits) for 500 sampled decisions;
Spearman rank correlation between |surrogate SHAP| and |gradient SHAP| over the 32
features per decision, mean reported. Attributions are in logit units on both sides,
so the comparison is meaningful despite raw-vs-normalized inputs.

**Flip probes.** For each card, sweep the top driver features one at a time across
their physical range with all else fixed, querying the **true policy**
(deterministic), and record where the action flips. The mask is **recomputed per
sweep point** via `build_mask` (every input is recoverable from swept obs + recorded
scenario constants) — sweeping wetness or SOC crosses mask thresholds, and a fixed
mask would assert flips through states where the swept action is illegal. Only
continuous dims are sweepable (a declared table in features.py; one-hots and binaries
excluded; the tri-state tyre-temp dim sweeps {0, 0.5, 1}). Flip points are translated
to physical units via the configs/env.yaml obs normalisers ("stays out until
tyre_age_norm = 0.42, i.e. about 17 laps").

**Cards.** One JSON per decision: named state (FEATURE_NAMES mirrors observation.py),
masks with reasons (straight from the env info dict), action, per-head probs (masked —
what the agent could actually do), per-head top-5 TreeSHAP drivers with the headline
drivers and flip line keyed to the pit head, plain-language line (deterministic
template over the top drivers and action), honesty footer with the per-head fidelity
badge and model_version. Persisted to Postgres `agent_decisions` under one
`SimulationRun` per eval race (model_version + env_config_hash + a `purpose:
"F09-eval-cards"` discriminator with circuit and seed in the config JSONB). The writer
delete-and-rewrites all rows for (model_version, purpose) in one transaction, so `make
explain` is idempotent. Surrogate boosters, fidelity.json, background composition and
an artifact manifest (sha256 of boosters, data fingerprint, model_version, git commit —
the F-23 honesty pattern) live under `models/explain/<model_version>/`.

**models/ is fully gitignored** (verified: `git ls-files models/` is empty), so the
committed record of the fidelity badge and rank correlation is
docs/results/F09-explainability.md — and F10's worker image build must COPY
`models/explain/<model_version>/` alongside the triplet (handoff note for the F10
plan).

## Deliverables

- `configs/explain.yaml` — every F09 constant with provenance (table below)
- `senna/explain/__init__.py` — package
- `senna/explain/features.py` — FEATURE_NAMES (32, mirroring observation.py), the
  sweepable-dims table with physical ranges and unit translations, phase derivation
- `senna/explain/dataset.py` — DecisionLogger policy wrapper (records raw obs,
  mask+reasons, unmasked+masked per-head probs), rollout driver reusing
  `run_episode`, derived-seed generation, pair dataset with episode-level split
- `senna/explain/surrogate.py` — row-expansion distillation per head, deepen ladder,
  masked fidelity (top-1 + KL), the hard gate, artifact writing with manifest
- `senna/explain/background.py` — stratified 1,024-state sampling + composition JSON
- `senna/explain/attributions.py` — TreeSHAP per decision, top-k drivers, additivity
- `senna/explain/crosscheck.py` — GradientExplainer wrapper module, 500-decision
  Spearman rank correlation
- `senna/explain/flip.py` — mask-recomputing single-feature sweeps on the true policy,
  flip detection, physical-unit translation
- `senna/explain/cards.py` — card assembly (5.8.3 fields + 5.3.5 payload), the
  version-mismatch refusal
- `senna/explain/persist.py` — transactional delete-and-rewrite of SimulationRun +
  AgentDecision rows (asyncio.run wrapper, the ingest pattern)
- `senna/explain/run.py` — CLI orchestrating distill -> gate -> background -> SHAP ->
  cross-check -> flips -> cards -> persist; sets `OMP_NUM_THREADS=1` before the first
  heavy import (the arm64 OpenMP clash), with a comment naming the finding
- `Makefile` — `make explain` (reads Postgres + models/headline — local, never CI),
  recipe env carries `OMP_NUM_THREADS=1`
- `tests/explain/` — the suite below (+ conftest with a tiny MaskablePPO fixture)
- `notebooks/fit_surrogate.ipynb` — fidelity/agreement/KL/rank-corr plots calling
  importable senna.explain functions (the one-notebook-per-fitted-module rule)
- `docs/results/F09-explainability.md` — the committed readout: per-head fidelity
  badge, mean KL, rank correlation, background composition, card counts, all keyed to
  model_version (written during /ship with the real numbers)

## Constants & configs

All new constants live in `configs/explain.yaml`:

| Constant | Value | Origin |
|---|---|---|
| `fidelity.threshold` | 0.90 | sourced 5.8.2 — the hard gate, per head |
| `distill.pairs` | 200000 | sourced 5.8.2 |
| `background.size` | 1024 | sourced 5.8.2 |
| `crosscheck.sample` | 500 | sourced 5.8.2 |
| `cards.top_k_drivers` | 5 | sourced 5.8.3 / A-03 |
| `distill.holdout_episode_frac` | 0.2 | stylised — episode-level fidelity holdout |
| `distill.soft_label_weight_floor` | 0.01 | stylised — row-expansion weight floor |
| `distill.xgb_ladder` | depth 6/est. 300 -> 8/600 -> 10/1200, lr 0.1 | stylised — the "deepen the surrogate" rungs (5.8.2) |
| `distill.rollout_seed_base` | 20260720 | stylised-frozen — the derived-seed root |
| `distill.seed_floor` | 1000000 | stylised — bank disjointness by construction (all frozen banks are 6-digit) |
| `background.phase_thresholds` | early < 0.25, late > 0.75 | stylised — lap-fraction phase bands |
| `flip.sweep_points` | 64 | stylised — grid resolution per sweep |
| `flip.features_per_card` | 2 | stylised — 5.8.3's example shows two flip conditions |

## Tests first

Written and shown failing before implementation, `tests/explain/`:

- `test_gate.py::test_pipeline_refuses_cards_below_fidelity` — the feature spec's row
  one: a surrogate under threshold means no cards, no partial output
- `test_gate.py::test_deepen_ladder_retries_before_refusing` — rungs tried in order,
  refusal only after the last
- `test_attributions.py::test_treeshap_additivity` — **property test** (hypothesis):
  attributions + expected value == class margin on sampled decisions
- `test_flip.py::test_flip_probe_finds_known_threshold` — a hand-built monotone policy
  flips exactly where constructed
- `test_flip.py::test_sweep_recomputes_mask` — a wetness sweep crossing a mask
  threshold never reports a flip onto an illegal action
- `test_features.py::test_feature_names_match_obs_dim` — 32 names, no gaps
- `test_features.py::test_perturbation_maps_to_named_dim` — altering one physical
  quantity in a built state changes only the named dimension (drift guard on the
  names↔indices mapping)
- `test_dataset.py::test_probs_respect_masks` — masked actions carry ~0 masked
  probability; unmasked heads sum to 1 (tiny MaskablePPO fixture)
- `test_dataset.py::test_holdout_split_is_episode_level` — no episode straddles the
  split
- `test_dataset.py::test_derived_seeds_disjoint_from_banks` — all derived seeds >=
  1,000,000; frozen banks untouched
- `test_surrogate.py::test_row_expansion_reproduces_targets` — expanded weights equal
  target probs; the floor drops what it should
- `test_surrogate.py::test_fidelity_measured_after_masking` — top-1/KL computed on the
  masked, renormalised surrogate distribution
- `test_cards.py::test_card_schema_complete` — state, masks+reasons, action, probs,
  top-5 per head, flip line, plain line, honesty footer with fidelity + model_version
- `test_cards.py::test_version_mismatch_refuses` — a surrogate for version A never
  explains triplet B (E-15 pairing)
- `test_crosscheck.py::test_rank_correlation_known_value` — synthetic attribution sets
  with a known Spearman
- `test_persist.py::test_rewrite_is_idempotent` — `make explain` twice leaves the same
  row count (skipif no DATABASE_URL, the tests/data pattern)
- `test_persist.py::test_run_row_carries_version_and_hash` — SimulationRun stores
  model_version + env_config_hash + purpose

`tests/explain/conftest.py` sets `OMP_NUM_THREADS=1` before torch/xgboost import —
any test exercising both in one pytest process hits the same segfault otherwise.

## Edge cases handled

- **E-15 (pairing)** — artifacts keyed by model_version; generation refuses a
  mismatch; the committed readout keys every number to the version string.
- **E-06 (held-out discipline)** — the F14 test bank is never read (the seeds.py guard
  refuses); distillation seeds are structurally disjoint from every frozen bank.
- **E-14 discipline, applied to fidelity** — episode-level holdout so the badge cannot
  be inflated by neighbouring laps of training episodes.
- **Mask not obs-recoverable** — distillation targets the unmasked distribution;
  fidelity is measured after masking, so the badge describes the surrogate exactly as
  cards use it.
- **Sparse strata** — SC/VSC × late × circuit cells can be empty; shortfall is
  redistributed proportionally and the composition JSON documents what was actually
  used.
- **Unfitted-compound guard (INDEX, 19 Jul)** — cards carry the mask reason codes
  verbatim, so an option that was off the table says why (including the
  `compound_unfitted_for_circuit` data limit).

## Acceptance checklist

- [ ] Cards exist for every eval race of the headline model (240 validation-bank
  races) in `agent_decisions`
- [ ] The fidelity badge value is stored per model version (fidelity.json +
  docs/results/F09-explainability.md)
- [ ] The cross-check rank correlation is computed and written down
- [ ] shap.TreeExplainer never touches the MLP directly (F-25 — structural, and the
  auditor confirms)

## Out of scope

- Serving cards over the API and the live per-lap card stream in the worker (F10 —
  which must COPY `models/explain/<model_version>/` into the worker image; handoff
  note)
- The dashboard SHAP panel and counterfactual view (F13)
- M1–M11 metrics, paired-seed counterfactual write-ups (F14)
- The rival-band sanity check flagged in INDEX stays an F14 to-do

## Decisions (Saad, 20 Jul 2026)

- **Q1, approved default:** `make explain` uses local Postgres (docker compose +
  DATABASE_URL), cards land in the real `agent_decisions` table per 5.3.5; every
  viva-critical number is also committed to docs/results.
- **Q2, approved default:** cards key the headline drivers and flip line to the pit
  head; both heads' top-5 attributions are stored.
- **Ship note 1:** F09 is tests-first, so run `rm -rf .ruff_cache && make lint`
  before the final gate — the warm-cache I001 trap that reddened F03–F06 must not
  recur.
- **Ship note 2:** surface the surrogate fidelity badge prominently in the ship
  report. If it lands under the 0.90 gate, stop and flag — never relax the gate
  silently.
