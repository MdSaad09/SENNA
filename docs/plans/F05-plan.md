# F05 — F1RaceEnv: observation, masks, dynamics, reward · approved plan

Depends on: F02 (Done), F03 (Done). Spec anchors: 5.5 (the whole section), E-01, E-03
to E-08, F-15 to F-20, A-01, A-10, plus F-05 (Manual Override).
Approved by Saad, 17 Jul 2026, with the three plan questions answered (see the change
log at the end). This is the heart of SENNA; the plan is long on purpose.

## Objective & spec anchors
Build `F1RaceEnv`, the Gymnasium environment: 22 cars, one decision per lap,
`MultiDiscrete([6, 4])` with per-head action masking, pure-numpy transition dynamics
with physics clipping, the exact three-term reward, and a 2024/2026 era switch —
100% regulatory legality by construction.

- **5.5.1–5.5.5** — the whole section is the contract: the 32-dim observation, the masks,
  the transition dynamics, the reward, and the info/reset behaviour, each implemented to
  the letter.
- **E-01** SOC depletion cascade → SOC hard-clipped to [0, 4] MJ; deployment requested
  above available energy is physically derated with an explicit lap-time penalty; the
  100k-random-action property test proves the bounds hold.
- **E-03** VSC is not SC → separate track states one-hot, separate pit-loss multipliers,
  separate lap-time multipliers. The lap-time multipliers are already fitted
  (`physics_params.globals.status_pace_2026`); the pit-loss multipliers are new.
- **E-04** red flag = free tyre change → a red flag neutralises the field and grants a
  compound choice to every car; it is an event, never a termination.
- **E-05** mass-pit ordering → the pit lane is a FIFO with per-car service-time draws;
  positions are recomputed from cumulative race time, never swapped in place.
- **E-07** backmarker traffic → all 22 cars share the pace/traffic model; overtaking a
  slower car costs a time penalty scaled by pace delta and override availability.
- **E-08** wet-transition cliff → wetness integrates sub-lap over three sectors, and
  compound validity is evaluated at pit-entry time.
- **F-15** the oscillation exploit that broke v2 → potential-based position shaping
  `Φ(s) = -0.1·position`, which telescopes to exactly zero over any closed loop.
- **F-16 / A-01** compliance is architecture, not reward: action masks plus physics
  clipping make legality 100% by construction; no term ever penalises an illegal action.
- **F-19** the observation drops v2's within-lap ERS quantity; it uses the previous lap's
  `last_lap_deploy_frac` feedback instead.
- **F-20** the mandatory two-compound rule is structural: stay-out is masked on the last
  feasible dry pit lap when `second_compound_used == 0`.
- **A-10** the era switch reads `physics_2024` / `physics_2026` yaml — one code path, two
  constant files.
- **F-05** the 2026 overtaking aid is Manual Override (gap ≤ 1.0 s, 350 kW held to
  337 km/h), never DRS.

**Divergences from the master spec, to flag (not master-vs-feature conflicts).**
Section 5.5.3 describes four quantities as "fitted" that no F02 notebook actually
produced: the status pit-loss multipliers, the dirty-air traffic magnitude, the weather
Markov matrix, and the wetness crossover thresholds. F05 lands them as `stylised`
constants in `env.yaml`, each comment naming the future feature and data source that
could fit it. We do not mislabel them `fitted`. Second, race distance (total laps per
circuit) lived nowhere in config — F03 read it from live data at fit time — so F05 adds
it to `circuits.yaml` (Q1 below).

## Deliverables

New package `senna/env/`, pure numpy and plain Python, with nothing pandas-shaped
reachable from `step()`:

| File | What, and why |
|---|---|
| `senna/env/__init__.py` | Exports `F1RaceEnv`. |
| `senna/env/race_env.py` | The `F1RaceEnv(gymnasium.Env)` class: `MultiDiscrete([6,4])` action space, `Box(-1, 1, (32,), float32)` observation, `reset(seed)`, `step(action)`, the info dict, and the era switch. All config dicts are cached in `__init__`/`reset`; `config.load` is never called from `step()`. |
| `senna/env/scenario.py` | Assembles a per-race scenario from configs (circuit slug, era, `race_laps`, grid, every fitted parameter) — extending the `validate._mc_spec` recipe with the energy, override and traffic constants. Builds the seed-driven equal-pace placeholder field of 22 cars. |
| `senna/env/state.py` | A struct-of-arrays `RaceState`: 22-wide numpy arrays for position, compound, tyre age, SOC, fuel, cumulative time, pit count, `second_compound_used`, and the rest. No per-car Python objects in the hot loop. |
| `senna/env/observation.py` | The 32-dim ego-centric encoder, exactly the 5.5.1 table — names, ranges, encodings — all scale-bounded to [-1, 1]. |
| `senna/env/masks.py` | Per-head mask functions returning a bit-vector plus reason codes (5.5.2), including the F-20 two-compound rule. |
| `senna/env/dynamics.py` | The joint lap-time model (5.5.3), harvest/deploy/derate with SOC clipped to [0, 4], all 22 cars vectorised. |
| `senna/env/events.py` | The track-status state machine (green/VSC/SC/red), the weather Markov chain and sub-lap wetness (E-08), the SC/VSC/red hazards, and tyre-failure-beyond-cliff → forced pit +25 s. |
| `senna/env/pitlane.py` | The FIFO pit lane with per-car service-time draws and cumulative-time re-ordering (E-05). |
| `senna/env/reward.py` | The three-term reward with per-lap decomposition: pace shaping, potential-based position, terminal points / 2.5. |

New config `configs/env.yaml` — the env-level constants (next section).
Changed config `configs/circuits.yaml` — a sourced `race_laps` per circuit.
Changed deps `requirements.in` and the re-locked `requirements.txt` — add `hypothesis`,
the home of the `property` marker ("first arrive with F05").
New tests under `tests/env/` mirroring the package, with a `tests/env/conftest.py`.

## Constants & configs

Everything the env reads that already exists is reused untouched: per-circuit
`t0 / t_ref / s_ref / sigma_driver / evolution / k_m / compound_offsets /
degradation(a,b) / pit_loss(mean,sigma) / hazards.λ` in `physics_params.yaml`;
`status_pace_2026.{sc,vsc}_lap_time_mult` and `k_m_pooled` in `physics_params.globals`;
`e_dep_mj / top_speed_kmh / shift_2026_logit` in `transforms.yaml`; `h_max_mj` in
`circuits.yaml`; and the 2026 power-unit, energy-store and `fitted:` block
(`conserve_pace_cost 0.423`, `attack_pace_gain 0.1411`, `derate_penalty 0.8368`,
`dirty_air_threshold 2.0`, `attack_soc_floor 0.5`) in `physics_2026.yaml`, with the 2024
counterpart driving the era switch.

New constants F05 introduces — name · value · origin · file:

Reward (`configs/env.yaml`, all sourced from spec 5.5.4 or FIA regs):
- `reward.pace_weight_w_p` · `0.02` · sourced (5.5.4)
- `reward.position_potential_coef` · `0.1` · sourced (5.5.4)
- `reward.points_divisor` · `2.5` · sourced (5.5.4)
- `reward.points_2026` · `[25,18,15,12,10,8,6,4,2,1]` · sourced (FIA 2026 sporting regs;
  the fastest-lap point is abolished — AR-11 / F-07)
- `reward.gamma` · `1.0` · sourced (finite-horizon race; the 5.5.4 magnitude arithmetic
  is undiscounted; PBRS telescopes to exactly zero on a closed loop only at γ = 1 — F-15).
  A comment records that F07's PPO discount must also be 1.0, or the mismatch is a
  conscious F07 choice (see change log).

Events and dynamics (`configs/env.yaml`):
- `forced_pit.tyre_failure_penalty_s` · `25.0` · sourced (5.5.3 / 5.5.5, kept from v2)
- `tyre_failure.cliff_age_margin_laps` · ~3 · stylised (laps past a compound's
  `max_age_seen` where the failure hazard engages; a survival fit on stint-end
  retirements could set it — F08)
- `tyre_failure.hazard_per_lap_beyond_cliff` · ~0.05 · stylised (same future fit)
- `pit_loss_mult.vsc` · ~0.65 · stylised (E-03; 5.5.3 anticipates a fit from 2022–2026
  neutralised stops — F06/F08)
- `pit_loss_mult.sc` · ~0.5 · stylised (E-03; the bunched field roughly halves relative
  pit loss; same future source)
- `red_flag.free_tyre_change` · `true` · sourced (E-04)
- `weather.n_sectors` · `3` · sourced (E-08)
- `weather.markov` · a 3×3 dry/damp/wet transition matrix · stylised (5.5.3 anticipates a
  fit from FastF1 weather traces — F06/F08)
- `compound_validity.slick_max_wetness` / `inter_band[low,high]` / `wet_min_wetness` ·
  ~`0.3` / `[0.25,0.75]` / `0.7` · stylised (E-08 mask thresholds; a crossover fit on wet
  races could set them — F08)
- `traffic.dirty_air_penalty_s` · ~0.4 · stylised (E-07 magnitude; the 2.0 s threshold
  already lives in `physics_2026`; era-scaled through the existing
  `aero.downforce_vs_2024 0.70`; a fit from stint-pace-in-traffic — F06/F08)
- `harvest.intra_lap_share` · ~0.5 · stylised (5.5.3 `intra_lap_share · harvest` — the
  fraction of this lap's harvest usable for same-lap deploy; a telemetry-integral fit — F08)
- `harvest.lift_and_coast_bonus_frac` and the clip handling · stylised (converts
  `lift_and_coast_kw` / `super_clipping_kw` and throttle-time into `H_lc` / `H_clip` MJ;
  braking harvest reuses `energy.braking_energy_mj_per_lap`)
- `pit.min_service_s` · stylised (the FIFO stacking floor; the per-car draw itself uses
  the existing `pit_loss.{mean_s, sigma_s}`)

Whether the policy is sensitive to any of these stylised values is an ablation question
for F08 and F14, not a thing F05 tries to settle.

Circuit distance (`configs/circuits.yaml`):
- `<circuit>.race_laps` · per circuit · sourced (the official published 2026 lap count,
  commented "scheduled race distance"; for a circuit with no raced 2026 event the
  305 km — 260 km at Monaco — distance rule over the lap length is the fallback)

## Tests first (each written and shown red before the code that greens it)

- `tests/env/test_masks.py` — one test per mask rule with its reason code: pit choices
  masked while the pit lane is closed; slicks masked above the slick-wetness threshold;
  Inter masked outside the damp band; Wet masked unless wet; attack (head B) masked below
  the `attack_soc_floor` of 0.5 MJ; defend never masked; and F-20 — stay-out masked on
  the last feasible dry pit lap when `second_compound_used == 0`.
- `tests/env/test_observation.py` — the observation is `shape (32,)`, `float32`, every
  dim inside [-1, 1]; each named dim encodes its 5.5.1 formula (spot-checking `soc_frac`,
  `override_available` flipping at a 1.0 s gap, and the one-hots summing to 1).
- `tests/env/test_dynamics.py` — the lap-time terms sum per 5.5.3; `deg = a·t0·age^b`;
  the SOC update clips to [0, 4]; the derate penalty is `p_der · max(0, D_request −
  deploy)` and is zero whenever supply meets the request.
- `tests/env/test_reward.py` — reward telescoping (F-15): an oscillating position sequence
  that returns to its start nets exactly zero shaping; the terminal
  `points_2026(pos) / 2.5` gives P1 = 10.0, P10 = 0.4, and 0 for out-of-points and DNF;
  all three terms appear separately in the decomposition.
- `tests/env/test_pitlane.py` — E-05: 22 simultaneous stops resolve by FIFO cumulative
  service time, never an in-place swap; the double-stacking loss grows monotonically with
  queue position.
- `tests/env/test_events.py` — E-03: VSC and SC apply different pit-loss multipliers and
  different lap-time multipliers; E-04: a red flag is not a termination and grants a
  compound choice to every car; tyre failure past cliff age forces a pit (+25 s) rather
  than terminating.
- `tests/env/test_determinism.py` — 5.5.5: `reset(seed=k)` followed by an identical action
  sequence reproduces a byte-identical episode across events, rivals and noise; different
  seeds diverge.
- `tests/env/test_properties.py` — property (E-01), `@pytest.mark.property` with
  hypothesis: 100k random action sequences, no masked action ever executes, SOC never
  leaves [0, 4], energy conserved to 1e-9 MJ.
- `tests/env/test_race_smoke.py` — a full 70-lap, 22-car 2026 race runs to `terminated`;
  a 2024-era race runs on the same code path (A-10); `info` carries the mask reasons and
  the reward decomposition every step; no pandas import is reachable from `step()`.

## Edge cases handled
- **E-01** SOC clip plus derate penalty plus the 100k property test.
- **E-03** separate track states, separate pit-loss and lap-time multipliers.
- **E-04** the red-flag handler, free tyre choice, no termination.
- **E-05** the FIFO pit lane and cumulative-time ordering.
- **E-07** all 22 cars in the traffic model, a dirty-air penalty on overtakes.
- **E-08** three-sector sub-lap wetness, compound validity checked at pit-entry.
- **E-06** (rival archetype degeneracy) is deferred to F06 — F05 uses the placeholder
  equal-pace field, so no archetype distributions live here yet. Noted, not handled.

## Acceptance checklist (the feature spec's "done means")
- [ ] The full 5.5 contract implemented: 32-dim obs, masks, dynamics, events, reward,
      info/reset.
- [ ] Every test above green, including the 100k-action property test and same-seed
      determinism.
- [ ] A 70-lap, 22-car race runs to completion in both the 2026 and 2024 eras.
- [ ] Mask reasons and the three-term reward decomposition appear in `info` every step.
- [ ] No pandas import reachable from `step()`.
- [ ] No inline physics constants; every number sourced, fitted or stylised in yaml
      (spec-auditor clean).

## Out of scope
Rival archetypes beyond the equal-pace placeholder and the train/test opponent split
(F06); throughput benchmarking and the 5.6.2 gate (F06); MaskablePPO training and the
curriculum (F07); any explainability logging beyond the raw per-step decomposition (F09).

## Change log — Saad's answers, folded in (17 Jul 2026)
1. **Q1, race distance.** Add a sourced `race_laps` to `circuits.yaml` using the official
   published lap counts, commented "scheduled race distance." The 305 km — 260 km at
   Monaco — distance rule over the lap length is the fallback only for a circuit with no
   raced 2026 event.
2. **Q2, discount.** `gamma = 1.0`, so the finite-horizon race is undiscounted and the
   F-15 telescoping is exact. A note in `env.yaml` records that F07's PPO discount must
   also be 1.0, or the PBRS mismatch is accepted as a conscious F07 decision.
3. **Q3, the "fitted"-but-unfitted constants.** Land them `stylised` in `env.yaml`; each
   comment names the future feature and data source that could fit it. Policy-sensitivity
   to these values is an ablation question for F08 and F14, not for F05.
