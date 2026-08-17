# F24 — tyre-model repair and headline retrain (approved 17 Aug 2026)

## Why this feature exists

Saad watched a live race (run 491, Australia, 17 Aug): the agent pitted on lap 3
and ran the same set of softs for 55 laps to P2. The decision card shows 99.2%
on that stop with stay-out fully legal, so it is the policy's genuine
preference, and the diagnosis showed why it is in-sim optimal:

- 37 of 145 fitted degradation curves carry `a = 0.0` — the 2026 SOFT at
  essentially every circuit, all three compounds at Canada. `deg = a·t0·age^b`
  with a = 0 means the tyre never loses lap time at any age.
- The T5 donor transfer propagates the zeros: Abu Dhabi's soft borrows from a
  donor pool whose members are all zero themselves.
- The likely mechanism is a bound-clip: the fitter bounds a >= 0, six rounds of
  2026 data carry track evolution that swamps the wear signal in short soft
  stints, and the optimiser pins to the boundary. A bound-clip is not a
  measurement, but it was stored as one.
- The UNFITTED_COMPOUND guard (masks.py, F08) masks compounds with *no* deg fit
  precisely because "no fit -> full grip, never wears". A present fit with
  a = 0.0 produces the identical never-wear tyre and sails through: the guard
  checks presence, not signal.
- The risk of running past the cliff is cheap: failure is a forced 25 s stop,
  not a DNF. M9 measured the habit at 37.9 failures per 100 races (target < 2)
  and the chapter links it to the M1 headline.

## Objective & spec anchors

Repair the fits so no served compound is ever free, guard the boundary so a
future zero cannot reach the env, retrain the headline under the repaired
physics, re-run the evaluation.

T5 (5.4) measured-beats-guessed ranks the repair ladder; E-10 requires a
bound-clip to be stored as unidentified, never as a curve; F-16/F-20 keep masks
as the compliance mechanism and the two-compound rule satisfiable; AR-18 lowers
confidence explicitly for prior-derived curves; R-12/5.6.1 keep budgets as
ceilings, curriculum and gates unchanged; E-15 forces re-distillation; A-09
requires the pack to round-trip after the re-freeze; M1–M11 re-run against the
frozen bars; F-26 keeps training out of serving.

## The repair ladder (approved design)

1. **Bound-clip detection.** A deg fit whose optimum lands on a = 0 is stored
   `identified: false` — it is a statement that the data could not measure wear,
   not a measurement of zero wear.
2. **Pooled refit.** Per compound and era, refit one (a, b) on the pooled
   partial residuals across all circuits — more data where per-circuit fits
   starve. A circuit whose own fit clipped takes the pooled curve,
   `source: pooled`.
3. **Cross-era prior.** If the pooled fit also clips, derive the curve from the
   same compound's identified fits in the other era, labelled
   `source: prior_cross_era` (approved default for Question 1: in-repo,
   citable, no external source needed).
4. **No free tyres backstop.** `build_scenario` refuses to serve a slick whose
   deg at its cliff age is zero unless it is excluded from
   `fitted_slick_actions`, and refuses the circuit outright if fewer than two
   dry compounds survive (F-20 must stay satisfiable).

## Constants

| Name | Value | Origin | Home |
|---|---|---|---|
| `deg.signal_floor_s` | 0.5 × s_ref at max_age_seen | operational — wear indistinguishable from lap noise over its own observed range is no signal | configs/fits.yaml |
| `scenario.min_dry_compounds` | 2 | sourced — F-20 unsatisfiable below it | configs/env.yaml |

No reward change (spec-locked, three terms). Hazard and forced-stop pricing
untouched — once old tyres bleed real lap time the gamble prices itself.

## Tests first

- bound-clipped fit is stored unidentified, never serialised as a curve
- pooled refit recovers known wear from synthetic residuals
- prior fallback carries its source
- property: every compound in `fitted_slick_actions` has deg(cliff_age) > 0,
  for every circuit-era build_scenario will serve — run 491 as an invariant
- fewer than two dry compounds refuses loudly
- regression by name: Australia 2026 SOFT, age 55, deg > 0
- existing engine golden fixtures pass untouched (pinned configs prove the
  engine didn't move, only the params)

## Compute (measured, models/runs.json)

One headline seed = full curriculum in 5–11 min on this Mac (18,477 env
steps/s, OQ-2); 3 seeds ≈ 30 min; finetune ≈ 5 min. Full pipeline: one
engineering session plus an afternoon of runs. Two 370-min outliers exist in
the ledger (throttling), so runs are not scheduled against a deadline.

## Approved defaults

- Prior derives cross-era from this repo's own identified fits (not external).
- Pre-repair evidence is archived: the F14 store copies to
  `docs/results/F14-pre-repair/` and the old headline stays in its run dir —
  the before/after comparison is part of the story.
- Expect M1 to shrink: the +2.28 was partly bought with free tyres. The story
  becomes capability traded for physical plausibility.

## Out of scope

Inverted compound offsets (reported in the fit diff, not repaired); reward
changes; failure-hazard re-pricing; UI work; the flaky tests/api slow tests
INDEX tracks.
