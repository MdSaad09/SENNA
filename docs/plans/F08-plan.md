# F08 — Ablations & headline runs — plan

F07 left a complete training pipeline: `train_run()` drives A→B→C with competence
gates, atomic checkpoint triplets, frozen seed banks and a W&B seam. F08 turns it into
the dissertation's evidence base: the four 5.6.3 ablations at 4M steps × 2 seeds, the
3-seed headline run, selection on validation seeds only, and a run ledger where every
row carries seed, config hash, budget and W&B id. Per the INDEX decision of 19 Jul,
the plan opens with the unfitted-compound mask guard — no run starts until the action
mask stops offering slicks the circuit has no degradation fit for. Compute: the env
steps cost ~50 minutes at the measured 18,477 steps/s, but Stage C evaluations (~60 s
each, ~40 per 4M arm, on the learner thread) dominate — the full slate is an
afternoon, shortened wherever stagnation stops fire early.

## Objective & spec anchors

- **5.6.3** — the ablation set, verbatim: (1) no curriculum, Stage C from scratch;
  (2) penalty-based constraints instead of masks; (3) v2's 12-term reward;
  (4) terminal-only reward; (5, optional) A2C at matched budget. 4M steps and 2 seeds
  each.
- **F-16 [CRITICAL]** — masks + physics clipping are the compliance architecture;
  ablation 2 is its direct test, "quantifies violations during learning and any
  final-policy gap". The penalty variant reproduces v2's architecture (clipping plus a
  penalty) — it never relaxes physical conservation, only converts discrete legality
  from masked-out to penalised-and-counted. The mask guard also lands under this
  anchor: it extends the F05 mask contract, which is why it opens this plan instead of
  landing as an F07 hotfix.
- **F-18 / F-22 / R-06** — DQN is excluded because SB3's DQN requires a flat Discrete
  space and the env is MultiDiscrete([6, 4]); the ablation budget is 4 runs × 4M × 2
  seeds precisely because v2's 8 × 20M grid was compute-impossible. The readout doc
  records the exclusion in those words — "itself a good viva answer".
- **5.7 Stage C** — checkpoint selection by validation-seed points; test seeds, the
  test rival band and the metric suite stay reserved for F14.
- **F-15 / F-17 / R-01 / R-02** — the master spec's "v2 says" quotes are the source
  for the 12-term reward reconstruction (coefficients below); the reimplementation
  must reproduce v2's known pathologies (the +0.2 oscillation pump) to be a faithful
  ablation arm.

**Design decision (approved — decision 2 below):** all four ablations run the Stage C
environment from scratch at 4M steps. Row 1 of 5.6.3 names that regime explicitly;
rows 2–4 are silent, and running them in the same regime makes ablation 1 the matched
control — ablations 2–4 then differ from it in exactly one axis, and the curriculum
question is answered by comparing ablation 1 against the headline's W&B curve at
matched global steps. The alternative — running 2–4 through the curriculum — would
need invented stage ceilings to fit 4M and would confound every comparison with the
gate schedule. Two consequences worth stating: the lr/ent schedules keep the global
8M horizon in every run, so an ablation's schedule position at step t is identical to
the headline's (the comparison depends on it — an arm ends mid-decay at lr ≈ 1.5e-4,
deliberately); and selection evals always run the default masked, v3-reward env, so
validation points are comparable across arms — the penalty arm is selected under
masking, its violations visible only in the training curves, which the readout says
out loud.

**Findings from planning (all verified in code by an adversarial review pass):**
1. `build_mask` (`masks.py:38`) never receives `available_compounds`; dry slicks are
   unconditionally legal. An unfitted slick borrows HARD's deg curve
   (`dynamics._compound_lookup`), reads as full grip in obs #9
   (`observation.py:16,41`) and gets the 40-lap fallback cliff — the "SOFT at Suzuka
   never degrades" exploit (Suzuka 2026 fits only MEDIUM and HARD). The F06 baselines
   already shop fitted compounds only, so the guard aligns the ego with the rest of
   the repo.
2. The pit lane is never closed in live play: `_pit_open` (`race_env.py:495`) returns
   True for every track status, so `PIT_LANE_CLOSED` is a dead branch at env level.
   The violations a penalty arm can actually surface are: the two-compound breach
   (last-lap stay-out, deterministic in a dry race), slick/inter/wet pits against the
   weather rules, attack below the SOC floor, and the new unfitted-compound rule —
   see finding 3 for why the last one stays structural.
3. Bypassing `_coerce` in penalty mode would let the ego pit onto an unfitted slick —
   reopening the exact exploit the guard closes. The unfitted-compound rule is a
   data-availability limit, not a sporting rule v2 ever penalised, so it stays
   coerced in every constraints mode.
4. Starting past Stage A without `--resume` raises (`run.py:152`), so the
   no-curriculum ablation needs an explicit `--fresh` flag (the accident guard stays).
5. `wandb_run_id` is `null` in every manifest on disk: `_WandbTracker` never exposes
   the id `run.py` reads via `getattr`. The ledger requires it, so F08 fixes the bug.
6. `run_id = "{date}-s{seed}-{fp12}"` — two ablation arms with the same seed and day
   would collide on run_id and run_dir. The arm id must enter the run identity.
7. Selection exists within a run (`gates.select_checkpoint`) and `best/` on disk does
   equal the recorded selection today, but only because `min_improvement_points` is
   0.0 — the coupling is fragile, so promotion asserts the `best/` manifest's global
   step equals the gate log's selected step instead of trusting it.
8. The v2 document is not in the repo (confirmed: F01 plan, "the v2 doc isn't in the
   repo"). Nine of the twelve reward terms have exact coefficients quoted in the
   master spec's "v2 says" rows; the fuel penalty's magnitude and the precise pace and
   terminal forms appear nowhere — hence decision 1.

## Deliverables

**0. The unfitted-compound mask guard (opens the feature, lands first)**
- `senna/env/masks.py` — `build_mask` gains a keyword-only `fitted_slick_actions`
  parameter (a pre-mapped set of legal slick action indices, default None = no guard,
  so the ~15 existing direct-call tests keep passing and masks.py stays free of
  compound-name knowledge). Dry slick actions outside the set are masked with a new
  `UNFITTED_COMPOUND` reason code.
- `senna/env/race_env.py` — the action-index set is computed once at construction
  from `scenario.available_compounds` and passed by `_ego_mask` (hot-loop: a frozen
  set built in `__init__`, no per-step work).
- The head-never-all-False invariant holds: `build_scenario` already refuses circuits
  with fewer than two fitted slicks, so even the F-20 last-lap forced pit always has a
  legal target. The identity fallbacks in `dynamics.py` and `observation.py` stay as
  safety nets but become unreachable for the ego.
- Every F08 run trains under the fixed mask. F07's single on-disk Stage A run predates
  it — the guard changes behaviour without changing configs, so that run's fingerprint
  would misleadingly survive; the run dir is archived before the ledger exists, and
  `git_commit` in every manifest is the pre/post-guard discriminator.

**1. Env variants (`senna/env/`)** — two new keyword-only kwargs on `F1RaceEnv`,
defaults reproducing current behaviour bit-for-bit (no RNG draw added or removed on
the default path), threaded through `stage_venv`'s existing `**env` passthrough:
- `constraints: "mask" | "penalty"` — under `"penalty"`: the true mask is still built
  internally every step (it is the violation detector and supplies the reason codes),
  but `action_masks()` returns all-True and `_coerce` lets the raw action through
  for every rule except `UNFITTED_COMPOUND` (finding 3). A wet-rule pit executes and
  is priced by the wetness physics; a last-lap stay-out finishes the race in breach;
  an attack below the SOC floor still derates physically — in each case the violation
  is counted in `info["violations"]` under the mask's reason code and fined the v2
  penalty in reward. `resolve_energy` is untouched: SOC stays in [0, 4] MJ and energy
  stays conserved in every mode. The readout pre-registers the expectation: early
  training should show real violation counts (exploration trips the SOC floor and the
  two-compound rule constantly); if steady-state counts fall near zero that is itself
  the F-16 result — capacity spent learning "don't press the illegal button".
- `reward_mode: "v3" | "terminal_only" | "v2"` — `"terminal_only"` drops both shaping
  terms (ablation 4); `"v2"` swaps in the 12-term reward. The decomposition contract
  is explicit: `info["reward_terms"]` always carries the three v3 keys (zero where a
  mode disables them) plus any variant terms, `total` equals the sum of reported
  terms in every mode, and `RewardTermsCallback` iterates the keys instead of
  hard-coding three — dominance ratio computed only in v3 mode, where it means
  something.
- `senna/env/reward_v2.py` (new) — the 12-term reward as pure functions, one per
  term, fixture-testable, coefficients from `configs/ablations.yaml`. The env accrues
  the small per-lap state v2's terms need and v3 never did — the field's running
  fastest lap, and recent pit/gap context for the undercut success rule — as
  numpy-only fields updated in `step()` (hot-loop discipline). Includes the undercut
  labelling rule and the fastest-lap check computed from race lap times (v3 has no
  fastest-lap action, R-01; divergence documented). The v2 reward's magnitudes are
  10–100× v3's and `VecNormalize(reward=False)` stays — any resulting value-function
  instability is part of the finding and the readout attributes it, not discovers it.

**2. Ablation harness (`senna/train/`)**
- `ablate.py` (new) — CLI (`python -m senna.train.ablate --run <id> --seed <s>`):
  reads the run matrix from `configs/ablations.yaml` and, rather than re-implementing
  `train_run`'s tail (tracker wiring, schedule/manifest closures, exit handling —
  ~100 drift-prone lines), generates a deterministic overlay configs dir (the
  `tiny_configs` copy-and-edit pattern from `tests/train/conftest.py`, promoted to
  production) whose Stage C carries the arm's env overrides and 4M ceiling, then
  calls `train_run(from_stage="C", to_stage="C", fresh=True, configs_dir=overlay,
  run_tag=<arm id>)`. The Stage C branch of `run.py` then wires `save_best`, the
  gate log and selection recording for free, and each arm's fingerprint is
  self-describing because its overlay bytes differ. `--dry-run` maps to the tiny
  profile so the whole matrix is proven in seconds before any real run — the feature
  spec's "harness proven before real hours burn".
- `run.py` — `--fresh` (finding 4); a `run_tag` that enters `run_id`, the run dir and
  the W&B run name (finding 6: `abl-<id>-<date>-s<seed>-<fp12>`); manifest rows gain
  the run kind.
- `tracking.py` — expose the W&B run id (finding 5) and tag runs
  (`headline` / `ablation:<id>`).
- `ledger.py` (new) — `models/runs.json`, one row per run: run id, kind/arm, seed,
  config fingerprint, budget ceiling, exit reason, W&B id, selected checkpoint,
  artifact paths. Crash-safe atomic writes on the `gatelog.py` pattern; incomplete
  runs are visible as such (the resume policy at this compute scale is
  restart-from-zero, and the ledger makes a restart honest instead of silent).
  `models/` is gitignored, so the ledger is the machine-readable working record —
  the committed paper trail is the readout doc below.
- `selection.py` (new) — cross-seed headline selection: best validation points across
  the three runs' selected checkpoints, ties to the earlier global step, then the
  lower seed (documented); `promote_headline()` verifies the chosen `best/` triplet's
  global step against the gate log (finding 7), then copies it atomically to
  `models/headline/` with a manifest naming the `model_version` string — the
  artifact F09 and F10 consume.
- **Makefile** — `make ablate RUN= SEED=`, `make headline SEED=`, and `make eval`
  (the stub F08 owns): score a run's checkpoints on the validation banks and write
  selection into the ledger. Same passthrough style as `make train`.

**3. The runs themselves**
- Four ablations × 2 seeds (`seeds.yaml train.ablation`, [101, 211]) × 4M.
- Headline: 3 seeds ([101, 211, 331]), full A→B→C under the 8M ceilings.
- Optional if the slate goes smoothly: (5) A2C at matched 4M × 2 — plain SB3 A2C on
  the default env, illegal requests handled by the existing `_coerce` snap
  (compliance stays by construction). It needs two carve-outs the maskable machinery
  won't give it: a policy shim (`Sb3Policy` passes `action_masks=`, which A2C
  rejects) and a load branch (`load_triplet` hardcodes MaskablePPO) — priced into
  "optional".
- `docs/results/F08-ablations.md` (new) — the committed paper trail: the run table
  (every row: seed, config hash, budget, W&B id) plus a one-paragraph readout per
  ablation, opening with the DQN exclusion in F-18/F-22/R-06 terms.
- A note for the reviewers: the penalty and v2-reward code paths are deliberate,
  spec-sanctioned deviations from the never-write table (5.6.3 rows 2–3
  are their charter); the variant modules carry that citation in comments so the
  spec-auditor flags nothing it shouldn't.

## Constants & configs

All new values live in `configs/ablations.yaml` with provenance comments; no existing
yaml changes value. `ablations.yaml` enters the fingerprint of ablation runs only
(via each arm's overlay) — the headline's 11-file fingerprint is untouched, so a
later coefficient edit can never silently break reproduce-by-hash for the promoted
model.

| Name | Value | Origin | File |
|---|---|---|---|
| budget_steps | 4,000,000 | sourced 5.6.3 | ablations.yaml |
| seeds | ref `seeds.yaml train.ablation` | sourced 5.6.1 (2 per ablation) | ablations.yaml |
| eval_every_steps | 98,304 | stylised — Stage C cadence reused | ablations.yaml |
| schedule horizon | global 8M kept in all runs | stylised — identical lr/ent position at matched global steps, the comparison 5.6.3 row 1 makes | ablations.yaml |
| runs.no_curriculum | Stage C env, no overrides | sourced 5.6.3 row 1 | ablations.yaml |
| runs.penalty_constraints | `constraints: penalty` | sourced 5.6.3 row 2 / F-16 | ablations.yaml |
| runs.reward_v2 | `reward_mode: v2` | sourced 5.6.3 row 3 / F-17 | ablations.yaml |
| runs.terminal_only | `reward_mode: terminal_only` | sourced 5.6.3 row 4 | ablations.yaml |
| runs.a2c (optional) | SB3 A2C, matched budget | sourced 5.6.3 row 5 | ablations.yaml |
| penalty.violation_penalty | −8.0 per breach | reconstructed — v2's −8.0 was the ERS penalty (F-16); extending it to every discrete breach is our reading, tagged as such | ablations.yaml |
| reward_v2.position_gain / .position_loss | +1.0 / −0.8 | sourced F-15 "v2 says" | ablations.yaml |
| reward_v2.sc_pit_bonus | +2.5 (first 2 SC laps) | sourced F-17 "v2 says" | ablations.yaml |
| reward_v2.ers_efficiency_coef | +0.1 × (deployed / E_dep) | sourced F-17; denominator reconstructed — v2's circular "circuit-optimal MJ" read as E_dep | ablations.yaml |
| reward_v2.grip_stint_end_coef | +0.2 × grip remaining | sourced F-17 "v2 says" | ablations.yaml |
| reward_v2.undercut_bonus | +0.5 | sourced F-17; success rule reconstructed, documented | ablations.yaml |
| reward_v2.ers_violation_penalty | −8.0 | sourced F-16 "v2 says" | ablations.yaml |
| reward_v2.tyre_failure_penalty | −12.0 | sourced R-02 | ablations.yaml |
| reward_v2.fastest_lap_bonus | +1.0 | sourced F-07 "v2 says"; computed from lap times, no action (R-01 divergence noted) | ablations.yaml |
| reward_v2.fuel_penalty + pace/terminal analogues | reconstructed values, flagged as such | decision 1 — no v2 doc exists | ablations.yaml |
| headline tie-break | earlier step, then lower seed | stylised — extends the 5.7 rule | ablations.yaml |

## Tests first

Written and shown failing before implementation. Existing suites (99/271/512/704/846)
stay green throughout — `build_mask`'s new parameter defaults to no-guard precisely
so the ~15 direct-call mask tests pass untouched; the 100k-random-action property and
`test_no_head_is_ever_left_all_false` are the standing regression bar for every mask
change.

`tests/env/` (suite seed 512):
- `test_dry_slicks_outside_available_compounds_are_masked` — Suzuka SOFT is masked
  with the `UNFITTED_COMPOUND` reason; **property** over seeds and laps.
- `test_fully_fitted_circuit_masks_are_unchanged` — Bahrain (all three slicks fitted)
  produces the identical mask as before the guard (default-drift pin).
- `test_random_legal_play_never_pits_onto_an_unfitted_compound` — **property**: no
  legal-action trajectory ever lands the ego on an unfitted slick.
- `test_default_env_is_unchanged_by_the_variant_kwargs` — `constraints="mask"`,
  `reward_mode="v3"` reproduce the no-kwarg env trajectory bit-for-bit.
- `test_penalty_env_reports_every_action_legal` — `action_masks()` is all-True.
- `test_penalty_env_permits_and_fines_a_two_compound_breach` — deterministic in a dry
  race: last-lap stay-out executes, the race finishes in breach, the violation is
  counted under the mask's reason code and the reward carries −8.0 — the feature
  spec's "otherwise ablation 2 measures nothing" pin.
- `test_penalty_env_counts_a_wet_rule_pit` — a slick pit above the wet threshold
  executes (priced by the wetness physics), counted and fined.
- `test_penalty_env_still_coerces_an_unfitted_compound` — the guard is structural in
  every constraints mode (finding 3).
- `test_penalty_env_still_clips_soc_and_conserves_energy` — **property**: E-01 holds
  in penalty mode; only discrete legality changed architecture.
- `test_penalty_env_counts_an_attack_below_the_soc_floor` — derate still prices it,
  and the request is counted and fined.
- `test_v2_reward_terms_match_the_quoted_formulas` — per-term fixtures against the
  F-15/F-16/F-17/R-01/R-02 quotes (the feature spec's fixtures test).
- `test_v2_position_terms_pay_the_oscillation_pump` — lose then regain a place nets
  +0.2: the reimplementation reproduces the exact pathology F-15 documents, which is
  the proof it is v2's reward and not a strawman.
- `test_terminal_only_reward_is_zero_until_the_flag` — and its terminal term equals
  v3's.
- `test_reward_decomposition_sums_to_total_in_every_mode` — the contract
  `RewardTermsCallback` iterates over.

`tests/train/` (suite seed 846):
- `test_every_ablation_config_dry_runs` — each arm in the matrix completes the tiny
  profile end-to-end: triplets, gate log and a ledger row exist.
- `test_two_arms_same_seed_get_distinct_run_dirs` — the finding-6 collision, pinned.
- `test_ledger_rows_carry_seed_hash_budget_and_wandb_id` — the feature spec's
  manifest requirement, field by field.
- `test_selection_code_cannot_read_the_test_bank` — the guard test: the F14-reserved
  loader refuses the harness, and no F08 module names the F14 consumer literal.
- `test_headline_selection_takes_the_best_validation_points_across_seeds` — ties to
  the earlier step, then the lower seed.
- `test_promotion_refuses_a_best_triplet_that_mismatches_the_gate_log` — finding 7's
  assert, plus the happy path: `models/headline/` is a complete triplet whose
  manifest carries the `model_version` string.
- `test_wandb_run_id_reaches_the_manifest` — the finding-5 bug, pinned with a stub
  tracker.
- `test_stage_c_fresh_start_requires_the_explicit_flag` — `--from-stage C` without
  `--fresh` or `--resume` still raises.

## Edge cases handled

- **E-01** — the penalty variant never relaxes physics: SOC clipping, deploy caps and
  energy conservation are identical in both constraint modes; the property test runs
  in both. Violations are illegal *requests*, penalised rather than masked.
- **E-06** — every F08 run, ablation and headline, draws rivals from the train band;
  the test band stays reachable only through the F14-guarded loader.
- **E-14 discipline, applied to RL seeds** — selection reads the validation banks
  only; the reserved test bank refuses every consumer but the F14 literal, and the
  guard test pins that F08 never names it.
- **F-20 × mask guard** — the last-lap forced pit always has a legal target because
  `build_scenario` refuses circuits with fewer than two fitted slicks.
- **DNF under the v2 reward** — the tyre-failure −12 fires on the forced-pit event
  (v2's semantics), not on termination; DNF terminal handling stays v3's
  (documented mapping in `reward_v2.py`).

## Acceptance checklist

- [ ] Mask guard landed: unfitted slicks masked with a reason code, property suite
      green — before any run starts; the pre-guard F07 run dir archived
- [ ] All four ablations (4M × 2 seeds) and the 3-seed headline complete within
      ceilings; curves in W&B
- [ ] A one-paragraph written readout per ablation in `docs/results/F08-ablations.md`,
      opening with the documented DQN exclusion (F-18, R-06)
- [ ] The chosen headline checkpoint is promoted to `models/headline/` and its
      `model_version` recorded — the artifact F09 and F10 consume
- [ ] Every run row in the ledger carries seed, config hash, budget and W&B id

## Out of scope

- The metric suite M1–M11, test-seed and test-rival-band reporting, counterfactuals
  (F14) — this feature produces models, curves and readouts, not the headline table.
- The SHAP surrogate (F09) and serving (F10) — F08 only mints and promotes the
  model version they consume.
- The rival-band sanity check against real pit-lap distributions (INDEX TO-DO,
  before F14's M1).
- Mid-stage checkpoint resume — runs are minutes long; restart-from-zero is the
  documented resume policy and the ledger records restarts honestly.
- Cheap sensitivity extras the configs already anticipate — gamma 0.999/1.0 one-line
  runs, the `carry_across_stages: false` re-warm — wired but not part of done; run
  them only if Saad asks after the core slate.

## Decisions (Saad, 19 Jul 2026)

1. **No v2 document exists.** The 12-term reward is reconstructed from the master
   spec's "v2 says" quotes (F-15/F-16/F-17/F-07/R-02); the roughly three unquoted
   values (fuel-penalty magnitude, the pace and terminal forms) are flagged
   `reconstructed` in the yaml and the readout carries the caveat. The qualitative
   conclusion — does heavy shaping hurt? — does not hinge on them.
2. **Ablation regime as proposed.** All four ablations run Stage C from scratch at
   4M; ablation 1 is the matched control for 2–4; the global 8M lr/ent schedule is
   kept in every run so schedule position matches the headline at equal global steps.
3. **W&B stays offline.** `mode: auto` without an API key logs offline; Saad decides
   separately whether to create a free account for browsable curves. Offline runs
   satisfy F08's done-means and sync later without loss.
4. **Ordering confirmed:** the mask guard lands, with its property suite green,
   before any run starts.
