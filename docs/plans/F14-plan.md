# F14 — Evaluation suite M1–M11 & era-matched counterfactuals — plan

F14 turns the frozen headline model into the dissertation's evidence chapter: all
eleven 5.12 metrics with bootstrap confidence intervals, the ten era-matched
counterfactual races, the sim-to-real numbers, and a `make report` that
regenerates the Chapter 7 tables deterministically. The repo has been preparing
for this since F06: the EventTrace pairing recipe is production code, all three
A-07 baselines exist, the oracle publishes its assumptions, a 480-seed test bank
sits behind a loader that only answers to the consumer string "F14", and the
serving counterfactual stamps `"era_matched_model": "pending-F14"` into every
run. Genuinely new: the metric implementations (no bootstrap/CI code exists
anywhere in the repo), the M5/M6 afterstate searches, the M11 variance
decomposition, the wet oracle extension, the 2024 Stage-C fine-tune (training is
era-pinned to 2026 today), nine of the ten real-strategy extractions,
`configs/eval.yaml`, and the committed run store. Compute is a non-issue: at the
measured 18,477 steps/s the fine-tune is ~30 minutes and the whole metric suite
~10 minutes of wall clock — OQ-9's "2–3 days" estimate predates the benchmark.

## Objective & spec anchors

- **5.12, all rows** — every metric ships with definition, target, denominator
  and its "how this metric lies" note; the notes travel into `configs/eval.yaml`
  as comments and into the report verbatim.
- **A-06** — paired-seed evaluation with bootstrap CIs. Pairing is on event
  traces, not raw seeds (INDEX decision, 19 Jul): one leg records with
  `record=True`, both legs roll on `reset(options={"twin": trace})`. M1 reuses
  `senna/train/gates.py::pair_outcome` (finisher beats DNF, both-DNF is no
  evidence, ties count against the agent).
- **A-05 / M3** — oracle regret against `solve_oracle`, whose seven published
  assumptions travel into the write-up. The oracle's in-code note assigns the
  wet extension to F14; it lands here.
- **A-07** — all three baselines exist (`heuristic.py`, `replay.py`,
  `random_legal.py`); M1 runs against the engineer heuristic, M2 against
  replayed real strategies with the `snapped` honesty counter.
- **A-08 / M11** — the luck-share decomposition the F06 trace machinery was
  built to enable.
- **F-24 / A-10 / OQ-9 (default confirmed: era-matched fine-tune)** — a quick
  Stage-C fine-tune on `configs/physics_2024.yaml`, then ten 2023/24 races
  replayed agent-vs-actual in the same simulator.
- **E-03** — M5 reports precision AND recall per neutralisation window, VSC and
  SC separated; the window definition (the denominator) is published.
- **E-14** — rounds 1–6 calibrate, 7+ test. F14 extends the existing three-layer
  guard (SQL filter, runtime refusal, AST import boundary) to the eval package.
- **E-04 / E-08** — red-flag races enter the ten only era-matched (the free tyre
  change rides in the trace); the wet-crossover ambiguity paragraph is the
  British GP entry's write-up.
- **INDEX obligations** — rival-band sanity check before M1's headline number;
  scripted baselines also run against the test band, framed as robustness;
  harvest-cap refinement re-verified before the headline runs (decision 1).

## Findings from planning (all verified in code)

1. `load_reserved_test_bank(consumer="F14")` (`senna/train/seeds.py:35`) is the
   only door to the 480 test seeds (20 × 24 circuits), and a tests/train guard
   keeps the literal "F14" out of `senna/train/` — the consumer call and the
   whole suite live in a new `senna/eval/` package.
2. M1's spec row says 500 paired seeds; the frozen bank holds 480. Expanding a
   frozen seed manifest post-hoc is worse than missing a round number: M1 runs
   on 480 and the divergence is documented in eval.yaml and the report.
3. No bootstrap, CI, afterstate or regret code exists anywhere; `scipy.stats`
   is already a dependency.
4. `stage_venv` and the eval loops are deliberately hard-wired to the train band
   and era 2026 (`envs.py:71`, `evals.py:24`). The band guard stays; era becomes
   config-driven (below) with default-drift pins.
5. `EpisodeResult` lacks the per-lap energy/status/derate/violation detail
   M4/M9/M10 need — `run_episode` gains optional per-lap capture, default-off,
   existing consumers bit-for-bit unchanged.
6. Decision timing drives M5/M6: the action for lap L is chosen against the mask
   built at the end of lap L−1, so pit-entry wetness for out-lap L is
   `trace.wetness[L-2]`, and a neutralisation starting on lap w1 is first
   observable at the decision for w1+1 — a pit on the onset lap was decided
   blind.
7. **Oracle stage-1 bug found while planning:** `_plan_table_cost` charges
   `pit_loss_mean_s` flat, ignoring the SC/VSC pit multiplier (0.5/0.65). On
   event-rich traces that overstates the best plans by ~8–12 s, can push them
   below the top-50 roll cut, and hands the oracle a beatable time — flattering
   M3. Fixed with the wet extension, with a test.
8. The wet extension is cheap: `stint_cost_table` needs zero changes (wetness
   already enters `lap_time_s` additively, never touches energy); only
   `enumerate_plans` learns wetness-dependent compound legality. A dry-only M3
   was weighed and rejected — with the markov weather chain only ~24–41% of
   races stay bone-dry, so the restriction would discard most of the bank. The
   dry subset stays as a reported robustness slice.
9. Twin replay is fully ego-counterfactual-safe (status, weather, failures,
   rival pits, service times, lap noise all read the trace or use means), so
   afterstate variants are well-defined. Published corollary: rivals do not
   react to a counterfactual ego stop (the oracle's assumption 2).
10. `MaskablePPO.predict(deterministic=False, action_masks=...)` samples the
    masked head and `model.set_random_seed` seeds python/numpy/torch — M11's
    decision-noise probe is implementable and reproducible.
11. `build_scenario(circuit, "2024")` silently falls back to 2026 fits for
    `canadian_grand_prix` and `french_grand_prix` (23 of 25 circuits carry
    genuine 2024 fits) — both are excluded from the ten and the fine-tune's
    circuit list, and the harness gains a strict-era guard.
12. `configs/real_strategies.yaml` holds 1 of the 10 M2 races; `extract.py` is
    winner-only, prints instead of writing yaml (its docstring claims
    otherwise), and keys drivers by number while the API keys by abbreviation.
    F14 unifies on abbreviation.
13. M8 as committed misses badly (KS 0.92/0.87 vs < 0.15) and covers only 2 of
    4 held-out rounds: round 7 vanishes via the `barcelona_grand_prix` /
    `spanish_grand_prix` slug mismatch, round 10 postdates the F03 run. The
    5.4.1 event-rate check (`rate_within_band`) exists but is never called.
    F14 fixes the aliasing, re-runs rounds 7–10, wires the dormant checks, and
    reports the miss with the F03 lesson's cause — refitting on held-out rounds
    stays forbidden (E-14).
14. `make eval` is taken (F08's rescorer); F14's targets are `make suite`,
    `make report`, `make finetune`.
15. `models/*` is gitignored — "deterministic given the run store" therefore
    means a committed store under `docs/results/F14/store/`, with the
    episode-grain raw store staying under gitignored `models/eval/`.
16. Every `circuits.yaml h_max_mj` is 8.5 with the same "no event-specific
    figure found" comment — the E-02 case the INDEX flagged (decision 1).
17. The DB was rebuilt 25 Jul (`agent_decisions` holds 288 rows, not F09's
    14,460). Nothing in M1–M11 reads `agent_decisions`, but the serving flip
    re-runs `make explain` for the 2024 model anyway (E-15).
18. The fine-tune's fingerprint cannot collide with the headline's: the overlay
    mutates `curriculum.yaml` (era, circuits, budget) and appends `eval.yaml`
    via `extra_config_files`, so `model_version` differs by construction.

## Deliverables

**0. Pre-flight gates (in order, before any headline number)**
- **Harvest-cap verification (E-02, INDEX debt):** verify the FIA 20 Apr 2026
  refinement (Issue 18 Art C5.2.10: recharge cap 8 → 7 MJ, quali floor 5 MJ,
  +0.5 MJ override under B7.2) against per-event values; record the outcome in
  `circuits.yaml` comments and the assumptions register. Default per decision 1:
  the headline evaluation keeps the constants the model was trained under
  (editing `circuits.yaml` now would desync the served fingerprint from live
  configs), and a sensitivity pass at `h_max_mj: 7.0` via a configs overlay
  shows the direction and size of the effect.
- **Rival-band sanity check (INDEX debt):** `senna/eval/band_check.py` —
  empirical pit-age-fraction distributions from ingested real races (2022–2026
  rounds 1–6 only; E-14-clean) via `laps.stint/tyre_life/compound`, compared per
  archetype band against `rivals.yaml pit_age_frac`. The report either passes
  the bands or documents the mismatch; M1 stays labelled provisional until this
  runs.

**1. The shared eval substrate — `senna/eval/` (new package)**
- `record.py` — for each (circuit, seed) in the reserved test bank (480 races):
  the frozen agent runs live on
  `F1RaceEnv(circuit, "2026", rival_band="test", record=True)`; the recorded
  trace saves to npz; the agent's twin roll of its own trace is the M3/M5/M6
  leg (deterministic ⇒ `ScriptedActions` over the realised action list reaches
  any branch point byte-exactly). Ego-DNF recordings excluded, counts published.
- `pairing.py` — M1 legs per the F06 convention: the engineer heuristic records
  live and donates the trace; both legs are twin rolls (self-pair = tie stays
  the invariant). Plus the INDEX robustness table: scripted baselines under
  train band vs test band on the same seeds, isolating opponent difficulty from
  the agent's gap.
- `senna/strategy/rollout.py` — `run_episode` gains optional per-lap capture
  (energy, track status, derates, violations, forced pits), default-off.

**2. Metric implementations**
- `bootstrap.py` — seeded percentile bootstrap; used by M1/M2/M6/M11.
- `metrics.py` — M1 (480 paired deltas + CI, target +1.0 with CI excluding 0),
  M4 (deployed/E_dep over green laps + derate share, from the live legs), M7
  (entropy of stop-count × first-stop compound, 1000 races/circuit on a
  documented seed derivation disjoint from the test bank), M9 (ego thermal
  failures per 100 races over the M7 batch), M10 (zero-snap assertion over
  every F14 rollout log + the standing 100k-random-action property test cited).
- `oracle_regret.py` (M3) — regret twin-vs-twin on the recorded traces; the
  agent's realised plan rides as `baselines=(agent_plan,)` so the oracle can
  only tie or beat it on the pit dimension; time regret primary, position
  regret via one extra roll of the oracle plan; negative regrets published as
  the greedy-energy assumption, never clipped.
- `senna/strategy/oracle.py` — the wet extension: compound legality per out-lap
  from `trace.wetness[L-2]` against the `compound_validity` thresholds
  (slicks ≤ 0.3, inter 0.25–0.75, wet ≥ 0.7), cliff caps via the existing
  fallback (43 laps), the two-compound rule waived unless the final decision
  row is dry; plus the status-aware stage-1 pit charge (finding 7). Dry traces
  pinned byte-identical by regression test.
- `afterstate.py` + `sc_quality.py` (M5) — windows = maximal same-status runs
  in `trace.status`, RED never a window (E-04); published denominator: one
  opportunity = a window with ≥1 informed in-window decision lap
  (w1+1 ≤ min(w2, last completed lap)); `SplicedPolicy(prefix, tail)` (new —
  `ScriptedActions` holds station after its script, wrong here); stay-out vs
  pit-at-k × legal-compound variants continue under the agent's own
  deterministic policy (not a re-optimised plan — re-planning would grade the
  call by a perfect future and conflate M5 with M3); labels PIT / STAY /
  immaterial with `label_margin_s: 1.0`; precision AND recall per status type;
  every exclusion class counted. Gaming note carried: the label is
  policy-dependent — an agent that follows up a stop badly excuses its own
  stay-out calls.
- `pit_accuracy.py` (M6) — per voluntary stop: sweep the stop lap across the
  corridor between neighbouring stops (cliff-cap and wet-legality filtered),
  full twin roll of the realised action list with only the pit head moved;
  `L′ = Lᵢ` must reproduce the base roll (built-in assert); hit iff within 3
  laps of the argmin (nearest-argmin on ties). Full rolls, not stint tables —
  the tables are blind to the SC pit multiplier, traffic and FIFO, exactly what
  moves optimal stop laps (~24k rolls ≈ minutes). The information-set statement
  is published verbatim: post-hoc coordinate-wise optimum on the frozen trace,
  other stops/compounds/energy fixed; the agent had no future knowledge; ±3
  laps is the allowance for that asymmetry.
- `luck.py` (M11) — live stochastic env, test band;
  `StochasticSb3Policy(model, normalize_obs, decision_seed)` samples the masked
  head; decision seeds nested in event seeds (a crossed ANOVA would be
  meaningless — RNG streams consume differently under different observation
  sequences); one-way random-effects method-of-moments per circuit over
  20 event seeds × 25 reps; luck share = the intraclass correlation of
  finishing position within event seed; within-seed event divergence is
  deliberately charged to the decision side, making the published share a
  conservative lower bound — stated in the report; CIs by bootstrapping event
  seeds (per circuit) and circuits (headline); mean head entropy reported
  alongside; degenerate cases (collapsed head → share 1.0 flagged; zero
  variance → NaN + flag) handled explicitly.

**3. M8 sim-to-real (reuse with three fixes)**
- Alias `barcelona_grand_prix` → `spanish_grand_prix` so held-out round 7 stops
  being silently skipped; re-run the 5.4.1 suite over all four held-out rounds
  (7–10, Belgium included); wire the dormant `rate_within_band` event-rate
  check and the energy-plausibility note into `run_validation`.
- M8 reads 2026 rounds ≥ 7 only through `senna/physics/synth/heldout.py` (the
  sanctioned door); `make report` reads the committed
  `docs/synth/validation_summary.yaml`, never re-queries. The KS miss is
  reported with the F03 lesson's cause.

**4. The 2024 Stage-C fine-tune**
- Era reaches training config-first: an optional per-stage `era` key in
  `curriculum.yaml`, read as `stage_cfg.get("era", "2026")` in `stage_venv`;
  `evals.py` drops its `_ERA` module constant for an `era="2026"` keyword
  threaded from the stage config; the Stage C evaluator filters the validation
  banks to the stage's circuit list (identity for the default 24). The
  committed `curriculum.yaml` never gains an `era` key — only overlays do — so
  the committed fingerprint is unchanged (pinned by test).
- `senna/eval/finetune.py` (pattern: `ablate.overlay_configs`): copytree
  configs, mutate `stages.C` only (era 2024, the 23 native-fit circuits, 2M
  ceiling), then
  `train_run(seed=331, from_stage="C", to_stage="C", resume=models/headline,
  configs_dir=overlay, run_tag="era2024", extra_config_files=("eval",))`.
  VecNormalize statistics carry in and keep adapting (F-23 continuity; the obs
  vector is largely era-relative by construction). Ledger `kind="era_finetune"`;
  promotion via the existing `promote_headline(candidate, dest=models/era2024)`.
- Acceptance A/B: the fine-tuned checkpoint beats the frozen 2026 headline
  evaluated on the same 2024 validation banks (one extra eval pass). If it
  doesn't: ship the miss documented, keep `pending-F14` (the serving flip has a
  graceful fallback), and the M2 write-up says which model produced the numbers.
- The borrowed 2024 `fitted:` energy coefficients stay borrowed — leverage is
  bounded by construction (2024's `e_dep_mj = h_max_mj = 2.0` vs ~9–12 MJ in
  2026) and a refit would touch frozen F03 code for days. Provenance: a
  `# borrowed:` block in `physics_2024.yaml`; the `scenario.py` note updates to
  "F14 keeps the borrow, sensitivity-checked"; the M2 battery re-runs with the
  four coefficients perturbed ±50% and the sensitivity rows commit to the store.

**5. Era-matched counterfactuals (M2)**
- **Real-events trace injection** (`senna/eval/traces.py`): the ten races'
  traces are synthesized from ingested data, not drawn from the markov chain —
  M2 is only meaningful against the events the team actually strategized
  around, and E-04/E-08 require the red flag and the wet crossover in the
  trace. Rules (each origin-labelled, a provenance sidecar per trace):
  status/red_flag from per-lap modal `track_status` digits (4→SC, 6/7→VSC,
  5→RED); wetness from `WeatherSample.rainfall` through the env's own
  integrator targets (the mapping is stylised and owns the E-08 ambiguity
  paragraph); grid from `SessionResult.grid_position` (pit-lane → back, short
  fields padded and counted); rival pits from every rival's real stints via
  `plan_from_rows`; `driver_s` drawn from the fitted distribution per race
  seed (declared synthetic); `failed` all False and rival modes balanced
  (stated). Serving's synthetic-dry shape is untouched.
- The harness (`senna/eval/harness.py`) re-implements the ~12-line pair loop
  offline (the worker function is coupled to Postgres/Redis): both legs on
  `F1RaceEnv(circuit, "2024", rival_band="test")` twin-rolling the synthesized
  trace — `RealStrategyReplay` (with `snapped` kept) vs the era-matched agent —
  over the first 5 test-bank seeds per race's circuit. Strict-era guard: a race
  whose scenario silently fell back to 2026 fits is refused.
- Statistics at n=10, stated up front: the exact paired sign test is the
  primary claim (9/10 wins ⇒ two-sided p < 0.05 — declared before the result);
  the bootstrap CI over ten per-race deltas is labelled descriptive; the full
  per-race table always shown.
- `extract.py` gains `--driver <abbrev>` (unifying on abbreviation) and
  `--write` (params_writer-style merge into `real_strategies.yaml`); nine new
  entries land with provenance.
- The ten races: `configs/eval.yaml m2.races`, frozen at /ship against actual
  ingest coverage — proposed list under decision 2.

**6. Serving flip (scope per decision 3; default: in)**
- `serve/loader.py::resolve_version` becomes a small registry driven by
  `serving.yaml baked_models: [headline, era2024]` — listed-but-absent dirs are
  skipped so a clone without the era triplet still serves; E-15 surrogate
  pairing unchanged. The "write the version string, keep running the 2026
  network" variant is rejected as dishonest; the real fallback is "don't flip".
- `explain/run.py` gains `--era` (its `_ERA` pin threads like evals.py);
  `make explain TRIPLET=models/era2024 ERA=2024` builds the 2024 surrogate
  under the 0.90 fidelity gate into `models/explain/<version>/`.
- `api/routes/counterfactuals.py` sets the era-matched `model_version` and
  writes the real version string into `era_matched_model`; on
  `UnknownModelVersionError` it degrades to today's exact behaviour
  (headline + `"pending-F14"`) instead of 500ing. Frontend needs no change
  (the flip is fixture-pinned); the two API tests that pin the literal update
  to read the expected string from the era2024 manifest. `.gitignore` gains the
  `models/era2024` and surrogate negations; `/agents` lists both models.

**7. Run store + `make report`**
- Gitignored raw store `models/eval/<model_version>/`: episode-grain jsonl per
  battery, M2 traces + sidecars, oracle search caches — the machine-readable
  twin, reproducible via `make suite`.
- Committed store `docs/results/F14/store/`: one JSON per metric at the
  smallest grain the figures need (`m1_pairs.json` 480 rows,
  `m2_races.json` incl. snapped counts and the ±50% sensitivity rows,
  `m3_regret.json`, `m4_energy.json`, `m5_windows.json`, `m6_pits.json`,
  `m7_entropy.json` as per-circuit histograms — 24k episodes never commit,
  `m9_failures.json`, `m10_legality.json`, `m11_decomposition.json`). Every
  file carries the A-09 envelope: model version(s), env config hash, seeds
  fingerprint, eval-config fingerprint, git commit.
- `make suite` → `python -m senna.eval.run` (with `--only`, `--smoke`);
  `make finetune` → `python -m senna.eval.finetune`;
  `make report` → `python -m senna.eval.report` — a pure function of the
  committed store + `configs/eval.yaml`: no env, no torch, no DB. Emits
  `docs/results/F14-evaluation.md` (the M1–M11 table: definition, value, CI,
  target, met/miss-with-cause, each 5.12 gaming note verbatim) and
  `docs/results/F14/figures/` (m1 delta histogram, m3 regret ECDF, m2 per-race
  dumbbell, m5 P/R by state, m7 entropy bars, m11 variance stack). Determinism:
  Agg backend, all randomness from the frozen bootstrap seed with per-metric
  substreams, no timestamps in the body; byte-identical on re-run, tested.
- Sequencing in /ship: pre-flight gates → era threading + eval.yaml + finetune
  module → launch `make finetune` (~30 min) → build harness/traces/metrics
  while it runs → explain-2024 + loader/route flip → extract the nine plans +
  freeze the race list → `make suite` → `make report` → commit store, doc,
  figures.

## Constants & configs

All in the new `configs/eval.yaml` unless noted; every entry carries its origin
and, for metric targets, the 5.12 gaming note as the comment.

| Name | Value | Origin |
|---|---|---|
| bootstrap.seed | 20260726 | stylised — frozen report seed |
| bootstrap.resamples | 10,000 | operational — CI stability at n=480 |
| m1.n_pairs | 480 | sourced 5.12, amended — frozen bank is 24×20; the 500→480 divergence documented here and in the report |
| m1.target_mean_delta / ci_level | +1.0 / 0.95 | sourced 5.12 |
| m2.target_mean_delta / stretch | +1.0 / +1.5 | sourced 5.12 |
| m2.seeds_per_race | 5 | stylised — per-race event repetition under the real trace |
| m2.races | ten {season, round, circuit, driver, rationale, red_flag, wet} entries | sourced — each entry cites its race; decision 2 |
| m2.trace.wet_after_laps | 3 | stylised — sustained-rainfall → WET target mapping (E-08 owner) |
| m3 | report-only note | sourced 5.12 — no hard target in run 1; search space stays `baselines.yaml oracle` |
| m4.target_utilisation / derate_max_share | 0.90 / 0.05 | sourced 5.12 |
| m5.precision_target / recall_target | 0.75 / 0.75 | sourced 5.12 |
| m5.label_margin_s | 1.0 | stylised — materiality band, far below half a pit loss; in-band windows excluded and counted |
| m6.tolerance_laps / target_share | 3 / 0.72 | sourced 5.12 (kept from v2) |
| m7.races_per_circuit | 1000 | sourced 5.12 |
| m7.seed_stream | documented SeedSequence derivation | operational — disjoint from the test bank and suite seeds |
| m9.max_failures_per_100 | 2.0 | sourced 5.12 |
| m11.decision_reps | 25 | operational — between-seed df (19) is the bottleneck; more reps buy nothing |
| m11.decision_stream | 173 | stylised — sub-stream id, disjoint from rollout's 91 |
| m11.bootstrap_resamples | 2,000 | operational |
| era_finetune.era | "2024" | sourced F-24 / OQ-9 default |
| era_finetune.resume | models/headline | operational |
| era_finetune.circuits | the 23 native-2024-fit circuits, listed explicitly | sourced — fit coverage; frozen-list-beats-computed per the F07 precedent |
| era_finetune.budget_steps | 2,000,000 | stylised — half the Stage C ceiling: a warm start adapts, it does not discover; a ceiling, never a schedule (R-12) |
| era_finetune.eval_every_steps / stagnation | 98,304 / 1,000,000 | sourced — curriculum Stage C row |
| serving.yaml baked_models | [headline, era2024] | operational — loader registry (deliverable 6) |

M8's targets are not duplicated: the suite keeps reading
`synth.yaml validation.{ks_target, pit_tolerance_s}`. The tests/eval suite seed
is 1187 (next in the 99/271/512/704/846 convention, disjoint from the 6-digit
seed banks).

## Tests first

Written and shown failing before implementation; existing suites stay green.
`tests/eval/` is a new package, suite seed 1187, with a conftest on the
`tests/strategy` pattern (`green_trace`, `make_env`).

Feature-spec pins:
- `test_m1_reproduces_known_deltas_on_hand_built_races` — two scripted policies
  with a constructed finishing gap on hand-built traces: mean delta and CI
  reproduce the known values; self-pair is a tie.
- `test_bootstrap_ci_covers_at_nominal_rate` — **property**: on synthetic
  distributions with known means, the 95% CI covers at ≈ the nominal rate.
- `test_m5_precision_recall_per_window_vsc_and_sc_separated` — hand-built
  windows, E-03 separation, always-pit inflates recall but not precision.
- `test_split_guard_2026_calibration_rounds_fail_loudly` — any eval entry point
  fed rounds 1–6 as validation raises, naming the rounds (E-14); plus the AST
  import-boundary test extended to `senna/eval/` (only the sanctioned M8 module
  reaches `heldout`).

Oracle (tests/strategy):
- `test_dry_enumeration_unchanged_by_the_wet_extension` — byte-identical pin.
- `test_wet_enumeration_respects_pit_entry_legality` — **property** over
  wetness ramps: every enumerated plan twin-rolls with realised pit laps and
  compounds equal to the plan (no silent snap).
- `test_stage1_pit_charge_is_status_aware` — the finding-7 fix: an SC-window
  stop table-ranks above its green-shifted copy.
- `test_regret_is_zero_when_the_agent_plays_the_oracle_plan` — and ≥ 0 with
  the agent plan as contender.

Afterstate (tests/eval):
- `test_window_extraction_on_handbuilt_status_arrays` — VSC/SC runs split, RED
  excluded, onset-on-final-lap and post-finish windows dropped and counted.
- `test_spliced_policy_prefix_reproduces_the_base_roll` — exact identity.
- `test_m5_labels_on_a_constructed_sc_window` — old tyre → PIT; fresh tyre →
  STAY; margin-band windows excluded from both numerator and denominator.
- `test_m6_sweep_identity_tie_rule_and_legality` — sweep contains Lᵢ and
  reproduces base time to 1e-6; nearest-argmin ties; wet-illegal and
  cliff-breaching laps absent; red-flag and forced stops excluded with counts.
- `test_m6_constructed_hit_and_miss` — a plan 5 laps off the argmin misses; at
  the argmin hits.

M11 (tests/eval):
- `test_stochastic_policy_is_reproducible_and_divergent` — same (seed, rep) ⇒
  identical actions; different rep ⇒ divergence on a live env.
- `test_mom_estimator_recovers_known_variance_components` — synthetic Gaussian
  grids, clipping at zero, degenerate grids (share 1.0 flagged / NaN flagged).

Fine-tune & era (tests/train):
- `test_committed_config_fingerprint_is_unchanged` — the era key exists only in
  overlays.
- `test_stage_venv_without_era_key_builds_2026_bit_for_bit` — default-drift pin.
- `test_finetune_overlay_mutates_only_era_circuits_budget` — golden overlay.
- `test_tiny_finetune_records_resumed_from_and_a_distinct_model_version` —
  tiny-profile smoke via the dry-run path.

M2 & traces (tests/eval):
- `test_trace_synthesis_from_handbuilt_rows` — status digit mapping, lap
  rescale, pit-lane grid placement, short-field padding, `_check_twin`
  acceptance.
- `test_m2_race_guards` — non-2023/24 seasons refused; a circuit whose 2024
  scenario is the silent 2026 fallback (canadian_grand_prix) refused.
- `test_extract_writes_a_driver_entry` — `--driver`/`--write` round-trip into
  the new schema; `load_real_plan` reads it back.

Serving (tests/serve, tests/api):
- `test_loader_registry_resolves_both_baked_models` — unknown versions still
  refuse; a listed-but-absent dir is skipped.
- `test_counterfactual_route_degrades_to_pending_when_unbaked` — and sets the
  real version when baked (the two literal-pinning tests updated to read the
  era2024 manifest).

Store & report (tests/eval):
- `test_report_is_byte_identical_on_a_fixture_store` — run twice, compare.
- `test_store_rows_carry_the_a09_envelope` — versions, hashes, git commit.
- `test_m10_zero_snap_counter_over_rollout_logs` — a deliberately illegal
  scripted action is counted; agent logs count zero.

## Edge cases handled

- **E-02** — harvest caps stay config-only; the C5.2.10 verification and the
  7.0 sensitivity overlay are pre-flight gate 0 (decision 1).
- **E-03** — M5 separates VSC and SC end to end: separate windows, separate
  P/R, separate report rows; the status-aware pit charge prices them apart in
  M3's stage 1 too.
- **E-04** — RED laps are never M5 windows; red-flag pits are excluded from M6
  with counts; red-flagged real races enter the ten only era-matched, capped at
  two, with the free tyre change riding in the synthesized trace.
- **E-06** — training never sees the test band (the `stage_venv` guard stays);
  the eval package is the single consumer of the test band and the reserved
  bank; the fine-tune trains on the train band.
- **E-08** — compound legality is evaluated at pit-entry wetness
  (`trace.wetness[L-2]`) in the oracle, M5 variants and M6 sweeps alike; the
  rainfall→wetness mapping is stylised and owns the ambiguity paragraph in the
  British GP write-up.
- **E-14** — the split guard extends to eval: runtime refusal naming offending
  rounds, AST import boundary, and M8 reads held-out rounds only through
  `heldout.py`. The M8 miss is reported with cause, never refitted.
- **E-15** — the 2024 model ships with its own surrogate before it serves; the
  loader's pairing check is unchanged; the route degrades gracefully when the
  triplet is absent.

## Acceptance checklist

- [ ] Pre-flight gates ran first: C5.2.10 verification recorded; rival-band
      sanity check reported (M1 loses its provisional label or the mismatch is
      documented)
- [ ] Every M1–M11 number exists with a CI; targets met, or the miss documented
      with cause (M8 carries the F03 diagnosis; M2 carries the sign-test
      framing)
- [ ] `make report` regenerates the Chapter 7 tables and figures from the
      committed store, byte-identically
- [ ] The counterfactual numbers are final, era-matched, assumptions stated;
      `models/era2024/` is a frozen triplet with `resumed_from` in its manifest
      and a ledger row; `"pending-F14"` is cleared (or the documented fallback
      stands)
- [ ] The M1 harness reproduced known deltas and CI coverage on hand-built
      races before any real run; split guards fail loudly
- [ ] `docs/results/F14-evaluation.md` follows the F08/F09 pattern with the
      gaming notes verbatim and a "Reproducing this" block

## Out of scope

- Dissertation prose and demo assets (F15); the live-view 3D canvas recheck
  (F15 pre-video item).
- Retraining or re-promoting the 2026 headline — every 2026-era number is
  computed against the frozen `senna-ppo-6b6edb78d84e-C-00835584`.
- Fixing M8's KS miss by refitting the generator (E-14 forbids it) and any
  harvest-cap retrain (decision 1's default).
- Refitting the borrowed 2024 energy coefficients — kept as a stated,
  sensitivity-checked assumption; a refit would reopen frozen F03 code.
- Serving-side changes beyond the counterfactual flip: no new views, no
  frontend work (the flip is already fixture-pinned).
- The Madrid circuit (E-13) — it enters when its data does; nothing here
  hard-codes circuit counts.

## Decisions (Saad, 26 Jul 2026)

1. **Harvest cap (E-02 / C5.2.10): document, don't retrain.** The headline
   numbers run under the 8.5 training constant; the 7.0 sensitivity pass runs
   via a configs overlay. The report states explicitly that the sensitivity
   measures the *frozen agent's robustness under a 7 MJ cap* — not what a model
   re-optimized for 7 MJ would do. The C5.2.10 per-event verification is
   recorded in `circuits.yaml` comments and the assumptions register.
2. **The ten-race list stands as proposed** (2024: Bahrain VER, British HAM,
   Monza LEC, Spa RUS, Hungary PIA, Monaco LEC; 2023: Zandvoort VER, Las Vegas
   VER, Silverstone NOR, Barcelona VER — frozen at /ship against actual ingest
   coverage; Canada 2024 excluded by its missing 2024 fits). **No race is
   swapped out because the agent loses it.** The pre-registered exact sign test
   and the full per-race table stand regardless of outcome — the list freezes
   before the first M2 roll.
3. **Serving flip is in**, with the graceful `pending-F14` fallback. If F14
   runs too heavy in the session, the flip (deliverable 6) is the designated
   cut, deferred to F15 — the offline M2 numbers are never cut.

Process notes for /ship and /land:
- `rm -rf .ruff_cache` before the final lint gate — ruff's warm cache has
  hidden I001 on tests-first features before (F03–F06 lesson).
- Verify GitHub Actions goes green after /land (git-credential + curl; no gh
  installed).
