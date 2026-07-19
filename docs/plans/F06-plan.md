# F06 — Rivals, baselines, oracle & throughput — plan

F05 shipped `F1RaceEnv` with a placeholder field: 21 equal-pace rivals on one scheduled
mid-race stop to HARD, always in balanced mode. F06 builds everything the agent will be
measured against: three readable rival archetypes with a train/test parameter split,
the three scripted baselines, the DP oracle on a deterministic twin, and the measured
steps/s number that prices F07's training plan. F05 explicitly deferred all four here
(docs/plans/F05-plan.md:179-196).

## Objective & spec anchors

- **E-06** — archetype parameters (pit thresholds, SC response probability, pace sigma)
  drawn per race from documented distributions; a held-out evaluation band reserved.
  The degeneracy risk (one shared "pit under SC" rule → memorisable field response) is
  designed out via per-car Bernoulli SC responses with per-race probabilities.
- **A-05 / M3 (5.12)** — oracle = full-information DP strategist on the deterministic
  twin; search space published verbatim: "all pit-lap × compound plans × greedy energy
  schedule". Regret ships with the oracle's assumptions list.
- **A-07 (5.12)** — three scripted baselines: engineer heuristics / replayed real
  strategy / random-legal.
- **5.6.2** — steps/s across 12 workers for 100k steps; expect 1,000–4,000 aggregate;
  profile before touching budgets if below ~300/s.
- **5.7** — Stage A's solo reference is the oracle enumerator restricted to a green
  solo trace (1–3 stops × greedy energy); Stage B gates against the engineer baseline;
  Stage C draws rival params train-band-only. F06 shapes both for F07 reuse.
- **M5 groundwork** — the EventTrace capture/replay machinery is what lets F14 compute
  ex-post afterstate optima per neutralisation window later.

Findings to record (surfaced during planning, all verified in code):

1. **Spec tension, flagged per workflow**: M1's mitigation says "rivals fitted to
   data"; the F06 feature spec says the distributions are stylised. Proposed default:
   stylised now, published in rivals.yaml; before F14's M1 run, sanity-check the bands
   against the ingested pit-lap distributions and refit if they disagree.
2. **Policy-coupled RNG streams**: `events.tyre_failure` draws only past the cliff and
   `_pit_times` draws once per stopping car, so two policies on the same seed diverge
   in their event streams after the first different stop. Raw same-seed pairing is
   therefore not "identical event draws" (A-06/M1). The EventTrace is the honest fix;
   F14 must pair on traces, not raw seeds — decision recorded now.
3. **Bahrain 2026 SOFT degrades at exactly zero** (`a: 0.0`, low-confidence cluster
   transfer). Oracle/heuristic will look tyre-immortal on the demo circuit; the twin's
   hard-cap failure rule is what bounds stints. Tests avoid stint-length realism
   assertions on 2026 Bahrain; the oracle demo also runs era 2024 (A-10 path).
4. **2026 `deg_max_age` falls back to 40 laps** (no `max_age_seen` in transferred 2026
   fits, scenario.py:91), so rival pit thresholds on 2026 circuits read as fractions
   of 40 — noted in rivals.yaml so the numbers stay interpretable.

## Deliverables

**Rivals**
- `configs/rivals.yaml` (new) — three archetypes as readable rule sets: undercutter /
  tyre_saver / opportunist, each with `pit_age_frac`, `sc_response_prob`,
  `pace_sigma_mult` as disjoint train/test `[lo, hi]` bands, plus four field-level
  knobs; every value stylised with rationale.
- `senna/env/rivals.py` (new) — `ArchetypeBook` (parsed once, band overlap rejected at
  parse), `RivalDraw` (per-reset parameter draw off the env RNG), `draw_field()`
  (balanced-thirds 7/7/7 assignment, rng-permuted, so every race fields all three
  styles), `pit_choices()` (priority ladder: red flag → wet crossover with per-car
  jitter → two-compound backstop at `total_laps - 1` mirroring the ego mask → SC/VSC
  Bernoulli response on onset laps → green tyre-age threshold). Compound targets are
  legal by construction against `env.yaml compound_validity`; rival F-20 compliance
  becomes explicit rather than accidental. Rivals keep BALANCED energy mode and no
  archetype pace offset — both documented simplifications (mode variability is not an
  E-06 axis; a pace offset would correlate strategy style with car pace and confound
  M1).
- `senna/env/race_env.py` — constructor gains `rival_band="train"` (fails at
  construction on an unknown band; serving passes "test" per 5.9); reset replaces the
  `_rival_pit_lap` block with `draw_field`; `_advance_track_status` returns
  `(red_flag, onset)`; `_field_pit_choices` delegates to `rivals.pit_choices` and
  overlays the ego head; the noise draw becomes
  `rng.normal(0.0, s_ref_s * sigma_mult)` with the ego slot pinned to 1.0.
- `configs/env.yaml` — `placeholder_rival` block deleted (nothing else references it).

**Deterministic twin (A-05/M3, M5 groundwork)**
- `senna/env/twin.py` (new) — `EventTrace`: grid, driver offsets, per-lap realised
  status/red-flag/weather/wetness, per-lap-per-car failures and applied rival
  pit/mode arrays; `EventTrace.green()` synthetic factory; `.npz` round-trip under
  `data/traces/` (gitignored).
- `race_env.py` — two more keywords: `record=True` captures applied values per step
  (recording what was executed, after rival decisions apply — robust to rivals.py
  internals); `twin=trace` replays them: noise zeroed, pit service collapsed to
  `pit_loss_mean_s` (FIFO and SC/VSC multipliers still apply), ego tyre failure
  promoted to certainty past the cliff, non-ego behaviour verbatim. Six predictable
  branches per step — hot-loop cost ~zero. `_terminal_info` gains `race_time_s`
  (M3 is a time gap; Stage A's gate is a race-time bar — currently missing).

**Baselines (A-07) — new subpackage `senna/strategy/`**
- `policy.py` — `StrategyPolicy` protocol: `act(obs, info, mask) -> action`. Baselines
  see exactly what an agent sees (obs, info, flat mask), never `env._state`; plus
  `ScriptedActions` for replaying recorded action lists (the M5 branch-point tool).
- `rollout.py` — `run_episode(env, policy, *, seed) -> EpisodeResult` (final position,
  race_time_s, points, pit laps/compounds, actions, `snapped` count). Env stream =
  seed; policy stream = `default_rng([seed, _POLICY_STREAM])`. F07 gates and F14
  paired rollouts reuse this one driver.
- `heuristic.py` — `EngineerHeuristic`: weather first (thresholds read from env.yaml
  `compound_validity` — one truth, never duplicated) → SC/VSC opportunism → F-20
  backstop → deg trigger (`a·t0·age^b` cost threshold) → compound-by-laps-left wheel →
  SOC-aware mode rule. Legal by construction down its own ladder, never leaning on
  `_coerce`.
- `replay.py` + `extract.py` — offline extractor (pandas + DB allowed there only)
  compiles a real race's stops into a plain plan and writes
  `configs/real_strategies.yaml` (checked in — CI never touches the DB). Ships with
  the 2024 Bahrain GP winner (57 laps, identity lap map). Replay covers stops only
  (the env fixes everyone's start compound at MEDIUM — documented limitation), runs
  balanced modes everywhere (a 2024 strategy carries no 2026 energy decision), defers
  a mask-blocked stop up to 3 laps then snaps nearest-legal-harder, counting every
  deviation in `EpisodeResult.snapped`.
- `random_legal.py` — uniform over unmasked entries per head from the policy stream.
- `oracle.py` — two-level design. Stage 1: exact per-compound stint-cost tables under
  the frozen trace (O(L²) per compound, ~10k entries), then full enumeration of all
  1–3-stop plans (Bahrain 57 laps: 112 + 12,320 + 720,720 ≈ 733k plans, O(stops)
  lookups each — seconds, vectorised; naive full rolls would be ~42M env steps).
  Stage 2: top-K (50) table plans plus each baseline's realised plan re-scored by
  full twin rolls (traffic, pit FIFO, red-flag edge included — ~3k env steps).
  `greedy_mode()` evaluates all four modes against the actual
  `dynamics.resolve_energy`/`mode_pace_s` per lap and picks argmin(pace + derate)
  subject to the mask — zero drift from the env by construction. Seven-item published
  assumptions list in the docstring (full information, non-reacting rivals,
  deterministic physics, greedy-not-joint energy, MEDIUM start, 3-stop cap with
  top-K exact scoring, no replanning). `solo_reference()` = stage 1 on a green solo
  trace — literally F07's Stage A bar.

**Throughput (5.6.2) — new `senna/bench/`**
- `throughput.py` — `python -m senna.bench.throughput`; SubprocVecEnv × 12, seeded
  resets, untimed warmup, `perf_counter` around exactly 100k aggregate steps with
  per-step `action_masks` fetch on the clock (pricing the env as MaskablePPO drives
  it) and random-legal actions (exercising pit/FIFO/compound branches). Reports
  aggregate and per-worker steps/s, projected 8M-step hours, hardware, python,
  commit, config hash (new `config.fingerprint(names)` sha256 helper — the same hash
  `SimulationRun.env_config_hash` wants in F10). Below 300/s it prints the 5.6.2
  profiling guidance and the "flag to Saad, F07 plan changes" note; measurement, not
  a gate (exit 0).
- `Makefile` — new phony `bench` target with `WORKERS=`/`STEPS=` overrides.
- The measured number + hardware goes into the INDEX decisions log (OQ-2 replacement)
  at the end of /ship, per the workflow.

**Tests** — `tests/env/test_rivals.py`, `tests/env/test_twin.py`,
`tests/strategy/{conftest,test_random_legal,test_heuristic,test_replay,test_oracle}.py`,
`tests/bench/test_throughput.py`. Suite seed 704 (fits 99 / synth 271 / env 512
convention).

## Constants & configs

All new numbers stylised unless marked; every yaml value carries the provenance
comment naming its origin and rationale.

**configs/rivals.yaml** (all stylised; test band strictly disjoint from train,
pushed further toward each archetype's character):

| Constant | train | test (held out) |
|---|---|---|
| undercutter.pit_age_frac | [0.50, 0.70] | [0.38, 0.48] |
| undercutter.sc_response_prob | [0.45, 0.65] | [0.66, 0.75] |
| undercutter.pace_sigma_mult | [0.95, 1.15] | [1.16, 1.25] |
| tyre_saver.pit_age_frac | [0.80, 0.95] | [0.97, 1.05] |
| tyre_saver.sc_response_prob | [0.10, 0.30] | [0.02, 0.08] |
| tyre_saver.pace_sigma_mult | [0.80, 0.95] | [0.70, 0.78] |
| opportunist.pit_age_frac | [0.68, 0.82] | [0.55, 0.64] |
| opportunist.sc_response_prob | [0.60, 0.85] | [0.86, 0.95] |
| opportunist.pace_sigma_mult | [0.90, 1.10] | [1.11, 1.20] |

Field-level: `vsc_response_scale: 0.5` (VSC saves less than SC — E-03),
`sc_response_min_stint_frac: 0.35`, `green_stop_min_laps_left: 4`,
`wet_crossover_jitter: 0.05` (parse-enforced ≤ `slick_max_wetness − inter_band[0]`).
Slick preference orders per archetype (SOFT-first / HARD-first / MEDIUM-first).
Archetype assignment is structural (balanced thirds), not a yaml knob.

**configs/baselines.yaml**: heuristic — `deg_pit_threshold_s: 1.2`,
`min_stint_laps: 8`, `forced_compound_laps_left: 3`, `sc_pit_min_age_laps: 6`,
`vsc_pit_min_age_laps: 10`, `hard_min_laps: 22`, `medium_min_laps: 10`,
`conserve_soc_mj: 0.8`, `attack_soc_mj: 2.5`, `attack_gap_s: 1.5`,
`defend_gap_s: 1.0` (all stylised; wetness thresholds deliberately absent — read from
env.yaml). replay — `mode: balanced`, `defer_max_laps: 3`,
`snap: nearest_legal_harder` (stylised). oracle — `max_stops: 3` (sourced, 5.7's
1–3-stop reference + no ≥4-scheduled-stop dry race in the 2022–26 ingest),
`top_k_rolls: 50` (stylised), `tyre_failure: hard_cap` (stylised). bench —
`workers: 12` (sourced 5.6.1), `total_steps: 100000` (sourced 5.6.2),
`warmup_steps: 2400`, `circuit: bahrain_grand_prix`, `policy: random_legal`
(stylised).

**configs/real_strategies.yaml**: the extracted 2024 Bahrain winner plan — sourced
(FastF1 via `senna.strategy.extract`, provenance comment states the session).

## Tests first

Written and shown failing before implementation, per the workflow.

**tests/env/test_rivals.py**
- `test_the_same_seed_and_band_reproduce_the_rival_draws` (feature-spec test)
- `test_the_test_band_changes_the_draws_for_the_same_seed` — archetype assignment
  identical across bands (shared unit uniforms), parameters differ
- `test_train_and_test_bands_never_overlap_for_any_parameter` (feature-spec test —
  real yaml, all 9 pairs)
- `test_an_overlapping_band_is_rejected_at_parse`
- `test_an_unknown_band_is_refused_and_the_known_bands_are_named`
- `test_every_race_fields_all_three_archetypes` — 7/7/7 across seeds
- `test_drawn_parameters_stay_inside_their_band` — **property** (hypothesis over seeds)
- `test_sc_responses_vary_across_archetype_draws` — **the E-06 degeneracy test**:
  fixed mid-race state, SC onset under N draws → response vectors not all identical,
  responders and stayers both exist
- `test_rivals_never_fit_an_illegal_compound_for_the_wetness` — **property**
- `test_every_rival_runs_two_compounds_in_a_dry_race`
- `test_a_red_flag_gives_every_rival_a_legal_archetype_chosen_change`
- `test_rival_lap_noise_scales_with_the_drawn_sigma` — ego stays at `s_ref_s`

**tests/env/test_twin.py**
- `test_a_captured_trace_replays_to_a_byte_identical_deterministic_episode`
- `test_events_on_the_twin_do_not_shift_when_the_ego_strategy_changes` — pins the
  paired-seed fix (finding 2)
- `test_the_twin_zeroes_noise_and_collapses_service_draws_to_the_mean`
- `test_a_synthetic_green_trace_runs_an_all_green_dry_race`
- `test_a_trace_survives_the_npz_round_trip`
- `test_terminal_info_reports_the_ego_race_time`

**tests/strategy/**
- `test_the_random_legal_baseline_never_proposes_a_masked_action` (feature-spec test;
  **property** variant over seeds) + same-seed reproducibility
- `test_the_engineer_heuristic_finishes_with_a_legal_two_compound_strategy`
- `test_the_heuristic_takes_the_cheap_stop_inside_a_safety_car_window`
- `test_the_heuristic_fits_intermediates_when_the_track_wets`
- `test_every_heuristic_threshold_reads_from_baselines_yaml`
- `test_a_recorded_real_strategy_replays_its_stops_at_the_recorded_laps` (snapped == 0)
- `test_an_illegal_recorded_compound_defers_then_snaps_and_is_counted`
- `test_the_extractor_compiles_stints_into_a_plain_plan` — crafted frames, no DB
- `test_a_replayed_2024_strategy_runs_balanced_modes_everywhere`
- `test_the_stint_table_matches_an_independent_hand_computation`
- `test_the_oracle_beats_or_ties_every_baseline_on_a_deterministic_toy_race`
  (feature-spec test; baselines' plans injected into stage 2 make it hold by
  construction against plan-shaped strategies)
- `test_every_enumerated_plan_honours_the_two_compound_rule_and_the_stop_cap`
- `test_greedy_energy_never_picks_a_mode_the_dynamics_price_worse` — **property**
- `test_the_solo_reference_is_deterministic_across_calls` — F07's bar must be stable

**tests/bench/test_throughput.py**
- `test_the_bench_report_carries_hardware_commit_and_config_hash` — dummy vec, fast
- `test_the_harness_measures_subprocess_workers` — **slow**, 2 workers, ~300 steps

Existing suites (determinism, 100k-random-action property, race smoke, no-pandas
subprocess check) run unmodified and must stay green.

## Edge cases handled

- **E-06** — per-car Bernoulli SC responses with per-race drawn probabilities;
  balanced-thirds assignment guarantees all three styles every race; degeneracy test
  above.
- **E-03** — VSC ≠ SC: `vsc_response_scale` for rivals, separate
  `sc/vsc_pit_min_age_laps` for the heuristic; SC/VSC pit-loss multipliers still
  apply on the twin.
- **E-04** — the red-flag free change becomes archetype- and wetness-aware (the old
  placeholder fitted HARD unconditionally, even in a monsoon).
- **E-05** — pit FIFO preserved on the twin (service collapses to the mean; stacking
  stays deterministic given arrivals).
- **E-08** — per-car jittered wet crossover staggers the field's inter/slick calls
  (no memorable full-field pit train); jitter bound parse-enforced against
  `compound_validity` so a future crossover fit cannot strand a rival illegally.
- **F-20** — rival two-compound compliance made explicit (backstop mirrors the ego
  mask's `total_laps - 1` rule exactly); today it is accidental (MEDIUM start + HARD
  stop).
- **F-16** — baselines and rivals are legal by construction down their own ladders;
  nothing leans on `_coerce`.

## Acceptance checklist (feature spec "done means")

- [ ] All three baselines and the oracle complete a full race; rivals draw per the
      documented distributions
- [ ] The throughput number is measured and written down, hardware noted (INDEX
      decisions log, closing OQ-2's default)
- [ ] E-06 avoided: field response to a safety car is not a single memorable pattern
- [ ] If throughput lands under ~300 steps/s: stop, profile (`_tyre_failures` /
      `_field_pit_choices` / `_gaps_ahead` per-car loops are the first suspects),
      and flag to Saad immediately — the F07 plan changes

## Out of scope

- Training (F07); the metric suite proper and the other nine M2 extractions (F14)
- Fitting the stylised env.yaml multipliers (pit_loss_mult, weather markov, dirty
  air) — noted F06/F08 candidates, not blockers here
- Rival energy-mode variation and archetype pace offsets (documented simplifications)
- Start-compound choice for anyone (env fixes MEDIUM; outside the action space)
- M11 luck decomposition (F14, but the trace machinery here enables it)

## Decisions (Saad, 19 Jul 2026)

1. **Held-out band geometry: extrapolation-toward-character**, stated in the
   rivals.yaml header. Because the test band is deliberately harder, F14 must also
   run the fixed scripted baselines against the test band, so opponent difficulty is
   separated from the agent's generalisation gap — and the result is framed as
   **robustness to unseen-and-more-extreme opponents**, never as in-distribution
   generalisation. This framing note goes in the yaml header and carries into F14.
2. **Stylised now, with honest bands.** Tracked to-do (recorded in the INDEX
   decisions log): sanity-check the rival bands against the real ingested pit-lap
   distributions before F14's M1 run; **M1's headline number is provisional until
   that check passes**. If the bands disagree with the data, they get refit and
   relabelled `fitted` then.
3. **Throughput**: flag the measured number to Saad the moment it exists — not just
   in the ship report — and immediately if it lands under ~300 steps/s (the F07 plan
   changes).
