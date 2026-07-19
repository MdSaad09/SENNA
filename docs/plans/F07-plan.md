# F07 — Training: MaskablePPO + curriculum — plan

F06 left the agent's world complete: rivals drawn from banded archetypes, scripted
baselines, a deterministic twin for paired evaluation, and a measured 18,477 env
steps/s across 12 workers (docs/plans/F06-plan.md; INDEX OQ-2). F07 trains the agent
honestly on top of it: MaskablePPO with the 5.6.1 hyperparameters, three curriculum
stages that advance only on competence gates evaluated on frozen seed sets, and
checkpoints that ship as complete triplets. The compute answer makes this cheap — the
full 8M-step ceiling is ~20–35 minutes end-to-end on Saad's Mac — so the design
optimises for reproducibility and an honest paper trail, not for wall clock.

## Objective & spec anchors

- **5.6.1** — every hyperparameter lands in `configs/training.yaml` verbatim with the
  table's reasoning as comments; MLP pi=[256,256] vf=[256,256], 12 SubprocVecEnv
  workers, VecNormalize(obs=True, reward=False).
- **5.6.2** — already answered (OQ-2, measured 19 Jul 2026); no new benchmark needed.
- **5.7** — three stages with gates evaluated on frozen seed sets; VecNormalize
  statistics carry across stages (documented choice); gate values logged to
  `curriculum_gates.json`.
- **F-21** — no stage ever advances on step count alone. Gate decisions are pure
  functions with no budget input; a ceiling hit logs `budget_stop`, never a pass.
- **F-23** — weights + `vecnormalize.pkl` saved together atomically, config hash in the
  model version; round-trip integration test.
- **R-12** — A 1.5M / B 2.5M / C 4M are ceilings, never schedules; a gate-pass callback
  ends `learn()` early.
- **E-06** — Stage C trains on `rival_band="train"` only (a literal in the eval/factory
  code, never a parameter); the test band and test seeds are reserved for F14.
- **A-06 / INDEX decision (19 Jul)** — Stage B pairing uses F06 EventTraces, not raw
  seeds: record the baseline's races once, replay the agent on the twins.
- **F-15 / 5.5.4** — PPO gamma 0.997 vs the env's shaping gamma 1.0 is a conscious,
  documented mismatch (Saad's call, below); the dominance ratio is logged per run.
- **F-16** — masking stays the compliance architecture: sb3-contrib fetches masks
  natively through the vec stack; no reward penalties anywhere.
- **F-26** — wandb is imported in exactly one module (`senna/train/tracking.py`),
  training-side only; a test pins the discipline.

**Findings to record (surfaced during planning, all verified in code):**
1. **The solo reward is blind to pit loss.** `race_env.py:227` feeds
   `racing_time[ego]` (pit time excluded) into the reward; solo mode zeroes the
   position term and fixes the terminal at P1, so nothing prices a stop and Stage A
   would learn pit-happy behaviour. Fixed by a solo-only pace-term change (approved).
2. MaskablePPO 2.9 consumes masks via `env_method("action_masks")` through
   VecNormalize + SubprocVecEnv — no `ActionMasker` wrapper needed (verified in
   `.venv`: `sb3_contrib/common/maskable/utils.py`).
3. `learn(..., reset_num_timesteps=False)` treats `total_timesteps` as an increment,
   and SB3's `progress_remaining` re-anchors at every `learn()` call — so the spec'd
   linear schedules must be driven off the global step by a custom callback.
   `ent_coef` is a plain float in SB3, so its decay needs the same callback.
4. tensorboard is not a dependency, ruling out wandb's stock SB3 callback; a ~15-line
   SB3 `KVWriter` → wandb bridge replaces it.
5. Circuit availability: Monza and all six Stage B circuits are constructible today;
   24 circuits have end-to-end fitted params (`french_grand_prix` has only a hazards
   block — excluded). Monza's 2026 degradation is a low-confidence T5 transfer with no
   `max_age_seen` (uniform 43-lap cliff) — gate-coherent since the reference shares
   the model; one dissertation line.
6. `recorded_trace()` raises if the race never reached the flag; ego DNF is
   fuel-exhaustion-only, so the Stage B overflow seed bank is insurance, not a hot path.
7. `observation.py` divides by `n_cars - 1` → ZeroDivisionError at n_cars=1; a span
   guard (`max(n_cars - 1, 1)`) is part of the solo toggle.
8. No frozen RL seed banks exist anywhere. `configs/data_split.yaml` is the E-14
   round split — a different concept, untouched.

## Deliverables

**Env extensions (`senna/env/`)**
- `race_env.py` — three new keyword-only kwargs, defaults reproducing current
  behaviour bit-for-bit (no RNG draw added or removed on the default path):
  `solo: bool = False`, `weather: str = "markov" | "dry"`,
  `hazards: str = "full" | "sc_vsc" | "none"`. Touched sites: ctor (validate values,
  store, plus a twin shape guard: `twin.n_cars`/`n_laps` must match); `n_cars = 1 if
  solo`; `_max_red = 0` unless `hazards == "full"`; `_advance_track_status` returns
  green without rolling under `"none"`; `_resolve_weather` pins dry; `_tyre_failures`
  becomes the deterministic cliff cap under `"none"` (the twin's existing rule); the
  solo pace-term fix at `race_env.py:227` (pit time included when solo); `reset`
  honours `options={"twin": trace}` so Stage B evals reuse one env per circuit
  instead of re-parsing 2,268 lines of yaml per episode.
- `observation.py` — span guard for slots #2/#3 (identity at n≥2).

**Training package (`senna/train/`, new)**
- `run.py` — CLI (`python -m senna.train.run`) + the stage loop: one process runs
  A→B→C, `model.set_env(venv, force_reset=True)` then
  `learn(stage_ceiling, reset_num_timesteps=False)` per stage; the gate callback
  returns False on a pass, ending the stage early; a triplet saved at every stage
  exit. `--from-stage/--resume` restart at stage boundaries through the same
  triplet path (and give F08 its no-curriculum ablation for free).
- `envs.py` — stage venv factory: `assign_circuits` (deterministic, yaml-order;
  Stage A 12× Monza, Stage B 6×2 exact, Stage C `circuits[i::workers]`), a
  `CircuitCycler` env that rotates its pre-built envs per reset when a worker hosts
  more than one circuit, `Monitor`, then VecNormalize fresh (stage 1) or
  `VecNormalize.load(prev_stats, venv)` (carry).
- `model.py` — MaskablePPO built from training.yaml; triplet load onto a fresh venv.
- `callbacks.py` — `ScheduleCallback` (lr 3e-4→0 and ent_coef 0.01→0.002, linear over
  the summed 8M ceiling, driven by the global step), `RewardTermsCallback` (per-term
  episode means + dominance ratio from training `info["reward_terms"]`),
  `ThroughputCallback` (`perf/steps_s`), `GateEvalCallback` (every
  `eval_every_steps`: save `last/` triplet, run the stage's gate evaluation, log
  `gate/*` and `curriculum/stage`, update Stage C `best/`, stop the stage on a pass).
- `gates.py` — pure decision logic, numpy + dataclasses only, drivable by hand-built
  histories: `plateaued`, `stage_a_gate`, `pair_outcome`, `stage_b_gate`,
  `stage_c_stop`, `select_checkpoint`, `GateDecision(passed, reason, values)`.
  Plateau rule: best-of-last-3-evals vs best-before, relative improvement < 1% — the
  reading a slow creep cannot pass. Stage A time gate one-sided (≤ +1.5% of the solo
  reference passes; a >1.5% beat passes but logs an anomaly flag). Stage B: ties and
  both-DNF count against the agent; exactly 200 pairs or fail loudly. Stage C:
  best-so-far validation points, stop after 1M steps without improvement; selection
  = max points, tie → earlier step.
- `evals.py` — the episode loops: Stage A (100 frozen seeds, solo Monza env, mean
  race time vs `solo_reference` — computed once); Stage B (record the
  EngineerHeuristic's 200 races once per run with `record=True`, DNF'd recordings
  replaced from the frozen overflow bank and logged, traces saved as npz; per eval,
  replay the agent on each twin and compare classified positions); Stage C (mean
  points over 240 validation seeds, full stochastic env, train band). Plus the SB3
  policy adapter implementing the existing `StrategyPolicy` protocol:
  `model.predict(normalize_obs(obs), action_masks=mask, deterministic=True)` — the
  only place training statistics touch evaluation.
- `seeds.py` — bank loader; `load_reserved_test_bank(consumer=...)` raises unless the
  consumer is the literal "F14" (mechanical discipline for the held-out banks).
- `gatelog.py` — `curriculum_gates.json` writer (atomic tmp+rename): thresholds
  echoed verbatim, every eval's gate values with global step, transitions with named
  reasons, `budget_stop` distinct from any pass.
- `checkpoints.py` — atomic triplet save/load under
  `models/{utcdate}-s{seed}-{fp12}/stage{X}/{last,best,final}/`, `manifest.json`
  (fingerprint, git sha, stage, global step, seeds, circuit assignment, dominance
  ratio, wandb run id, library versions), and
  `model_version = "senna-ppo-{fp12}-{stage}-{step:08d}"` — the string F10 stores.
- `tracking.py` — the only wandb import. `Tracker` seam (no-op when disabled or init
  fails), SB3 KVWriter bridge for the native series, mode auto/online/offline/disabled.

**Configs** — `training.yaml`, `curriculum.yaml`, `seeds.yaml` (all new; schemas below).

**Makefile** — `make train` replaces the F07 stub, bench-style passthrough:
`SEED= FROM= TO= RESUME= STEPS= WANDB= WORKERS= VEC=`. Smoke:
`uv run make train STEPS=5000 WORKERS=2 VEC=dummy WANDB=disabled`.

**Tests** — new suite `tests/train/` (suite seed 846; existing suites 99/271/512/704
untouched) plus additions to `tests/env/`.

## Constants & configs

All new; every value carries a provenance comment in the yaml.

| Name | Value | Origin | File |
|---|---|---|---|
| ppo.* (n_envs 12, n_steps 512, batch 1024, epochs 8, lr 3e-4→0, gae 0.95, clip 0.2, ent 0.01→0.002, vf 0.5, grad 0.5) | 5.6.1 defaults | sourced 5.6.1 | training.yaml |
| ppo.gamma | 0.997 | sourced 5.6.1 — comment records the conscious mismatch with env.yaml reward.gamma 1.0 (F-15); 1.0/0.999 are one-line F08 runs | training.yaml |
| policy.pi / policy.vf | [256,256] / [256,256] | sourced 5.6.1 | training.yaml |
| schedules.horizon | global (summed ceilings) | stylised — per-stage decay would jump lr at every early gate exit | training.yaml |
| normalize.{obs,reward,carry_across_stages} | true / false / true | sourced 5.6.1 + 5.7 | training.yaml |
| tracking.{project,mode} | senna / auto | stylised | training.yaml |
| stage budgets | A 1.5M / B 2.5M / C 4M | sourced 5.6.1, R-12 ceilings | curriculum.yaml |
| stage circuits | A: italian; B: italian, spanish, british, belgian, japanese, monaco; C: the 24 fitted circuits listed explicitly | sourced 5.7 (OQ-7); C reading decided by Saad | curriculum.yaml |
| stage env toggles | A `{solo, dry, none}` · B `{full, dry, sc_vsc}` · C `{full, markov, full}` | sourced 5.7 rows | curriculum.yaml |
| gate.plateau_{window,improvement} | 3 / 0.01 | sourced 5.7 | curriculum.yaml |
| gate.time_tolerance | 0.015 (one-sided, anomaly-flagged beat) | sourced 5.7; reading documented | curriculum.yaml |
| gate.{finish_ahead_min, median_delta_min, n_pairs} | 0.55 / 0.0 / 200 (inclusive) | sourced 5.7 | curriculum.yaml |
| gate.{stagnation_steps, min_improvement_points} | 1,000,000 / 0.0 | sourced 5.7 / stylised | curriculum.yaml |
| eval_every_steps | A/B 49,152 · C 98,304 | stylised — 8 (16) rollouts of 6144; C's eval costs ~30–60 s, and its 1M stagnation window still spans ~10 evals | curriculum.yaml |
| plateau_denominator_floor | 1.0 | stylised — divide guard near zero return | curriculum.yaml |
| train.headline / train.ablation | [101, 211, 331] / first two | stylised-frozen / sourced 5.6.1 (3 seeds; 2 per ablation) | seeds.yaml |
| train.stage_offset | {A:0, B:1000, C:2000} | stylised — disjoint stage streams | seeds.yaml |
| eval.stage_a | 100 seeds | sourced 5.7 (size); values stylised-frozen | seeds.yaml |
| eval.stage_b | 200 (34/34/33/33/33/33 per circuit) + 24 overflow | sourced 5.7 (size); split + overflow stylised | seeds.yaml |
| eval.stage_c.validation / .test | 240 (10×24) / 480 (20×24, RESERVED for F14) | stylised — spec silent on sizes | seeds.yaml |

`seeds.yaml` carries a `frozen_on` header like `data_split.yaml`: editing after
training starts is seed-shopping. The run fingerprint extends the bench's file list
with training, curriculum and seeds.

## Tests first

Written and shown failing before implementation, per the workflow. Existing suites
stay green throughout.

`tests/env/` (suite seed 512) — the toggles:
- `test_default_env_is_unchanged_by_the_new_kwargs` — 22 cars, weather advances, hazards roll: pins against silent default drift.
- `test_solo_env_runs_one_car_to_the_flag` — n_cars 1, bounded obs, final_position 1.
- `test_dry_env_never_leaves_dry` — **property**: any seed, weather stays dry, wetness 0.
- `test_no_hazards_env_stays_green_all_race` — **property**: status green, no red flag, any seed.
- `test_no_hazards_tyre_failure_is_a_hard_cap` — forced pit fires at cliff+1, same lap every seed.
- `test_sc_vsc_hazards_never_raise_a_red_flag` — **slow**: seed scan on the highest-red-λ circuit; SC/VSC still occur.
- `test_solo_reward_pace_term_prices_the_pit_stop` — return difference across a stop ≈ w_p·pit_loss/s_ref (pins the approved fix).
- `test_a_mismatched_twin_is_refused` — 22-car trace into a solo env raises at construction.

`tests/train/` (suite seed 846) — gates on hand-built histories (feature-spec test a):
- `test_stage_a_gate_passes_on_a_flat_window_over_a_met_time_bar`
- `test_stage_a_plateau_is_not_fooled_by_slow_creep` — +0.9%/eval forever never plateaus.
- `test_stage_a_gate_needs_both_plateau_and_time` — either alone fails (F-21).
- `test_stage_a_time_gate_is_one_sided_and_flags_an_implausible_beat`
- `test_stage_a_gate_holds_once_triggered` — trigger-and-hold per the feature spec.
- `test_stage_b_thresholds_are_inclusive` — 0.55 and 0 pass; 0.549 and −0.5 fail.
- `test_stage_b_pair_outcome_orders_dnfs` — finisher beats DNF; ties count against the agent.
- `test_stage_b_gate_demands_exactly_n_pairs` — 199 pairs fail loudly.
- `test_stage_c_stagnation_clock_resets_on_improvement`
- `test_stage_c_checkpoint_selection_breaks_ties_toward_the_earlier_step`
- `test_no_stage_ever_advances_on_step_count_alone` — the named F-21 pin.

`tests/train/` — seeds, log, evals, loop:
- `test_seed_banks_are_sized_and_pairwise_disjoint` — sizes per seeds.yaml, no duplicates, disjoint from suite seeds.
- `test_the_test_bank_loader_refuses_f07` — the reserved-bank guard raises.
- `test_gate_log_round_trips_the_schema` — thresholds echoed, evals appended, budget_stop distinct.
- `test_solo_reference_matches_a_twin_roll_of_its_own_plan` — **property, slow**: rolling the reference plan through a solo green-twin env reproduces the table cost — the exactness proof behind the 1.5% gate.
- `test_stage_b_pairing_self_pair_is_a_tie` — **slow**: the heuristic replayed against its own trace: not ahead, delta 0 — the strongest single pin on the pairing harness.
- `test_stage_b_recording_replaces_a_dnf_seed_from_overflow` — recorder injected as a callable so the DNF path tests without a real fuel DNF.
- `test_checkpoint_roundtrip` — save triplet → load with training=False → identical VecNormalize stats and identical deterministic action on a fixed obs (the F-23 test).
- `test_wiring_smoke` — 256 steps, 2 DummyVecEnv workers, wandb disabled, stub gate: triplets exist, manifest complete, and the injected recording tracker saw every expected series (rollout/*, train/* incl. approx_kl, reward/* incl. dominance_ratio, perf/steps_s, curriculum/stage, gate/*).
- `test_stage_a_smoke_5k` — **slow**: the feature-spec smoke train, real Stage A config, one real gate evaluation end to end.
- `test_wandb_only_imported_in_tracking` — the F-26 discipline, mirroring the fastf1-only-under-data rule.

## Edge cases handled

- **E-06** — Stage C draws rivals from the train band only; `rival_band="train"` is a
  literal in the training factories and evals, the test band reachable only through
  the F14-guarded loader. Band disjointness already enforced at parse (F06).
- **E-03/E-04** — Stage B runs `hazards="sc_vsc"`: SC/VSC on, red flags off (red
  first appears in the 5.7 Stage C row); the red-flag path itself is untouched.
- **E-05** — solo pit lane degenerates to a queue of one at mean service on the twin,
  which is exactly what the reference's stint tables charge — the like-for-like basis
  of the Stage A gate.
- **DNF during Stage B recording** — `recorded_trace()` refuses an unfinished race;
  replacement comes from the frozen overflow bank in order, every substitution logged
  in `curriculum_gates.json` (fuel-only ego DNF makes this insurance).
- **E-14 discipline, applied to RL seeds** — `seeds.yaml` is frozen with a dated
  header before the first run; held-out test seeds are mechanically unreachable
  from F07 code.

## Acceptance checklist (feature spec "done means")

- [ ] Stage A trains to its gate within the 1.5M ceiling; gate values logged to
      `curriculum_gates.json`; every checkpoint on disk is a complete triplet
- [ ] A W&B run is reproducible from `seeds.yaml` plus the config hash (fingerprint
      covers env + training + curriculum + seeds; manifest records the rest)
- [ ] No stage ever advances on step count alone (F-21) — pinned by a named test and
      visible in the gate log's `budget_stop`-vs-`transition` distinction

## Out of scope

- Ablations, the 3-seed headline run, and full A→B→C production runs (F08 — the
  `--from-stage C` path exists but its ablation study is F08's).
- The SHAP surrogate — F07's "triplet" is weights + VecNormalize stats + manifest;
  the model triplet gains the surrogate in F09.
- Serving, `ModelVersion` rows, deployment (F10) — F07 only mints the version string.
- The rival-band sanity check against real pit-lap distributions (INDEX TO-DO,
  before F14's M1).
- Any fitting: Monza's low-confidence T5 degradation stands as-is (noted for the
  dissertation).

## Questions for Saad

1. **W&B account** — default `mode: auto` logs online when `WANDB_API_KEY` is set,
   offline otherwise, so training works either way. If you have no W&B account yet,
   nothing to do; runs land in the gitignored `wandb/` dir and sync later.
2. **Seed-bank sizes** — Stage C validation 240 and reserved test 480 are proposals
   (spec is silent). Cheap to enlarge before freezing, contamination to change after.
   Default: as proposed.
3. **Master-spec PDF rows F-21/F-23/R-12** — still unread pending
   `brew install poppler`; the extracted 5.6/5.7 sections carry each ID's substance
   and this plan cites them. Default: I read the raw rows at the start of /ship once
   poppler is in.

## Decisions (Saad, 19 Jul 2026)

1. **Solo reward prices pit stops** — the pace-shaping term includes pit time when
   `solo=True` only; documented divergence from the literal 5.5.4 table, pinned by
   `test_solo_reward_pace_term_prices_the_pit_stop`.
2. **PPO gamma 0.997** — master spec 5.6.1 wins over the env's shaping gamma 1.0;
   the mismatch is recorded in training.yaml as the conscious F07 choice env.yaml
   anticipates; gamma 1.0 / 0.999 noted as F08 sensitivity runs.
3. **Stage C circuit set = the 24 fitted circuits** — "all circuits with validated
   data" read as end-to-end fitted params (all but `french_grand_prix`), listed
   explicitly in curriculum.yaml and recorded in every run manifest.
