# F18 plan — Full-era refit and revalidation

Approved by Saad, 11 August 2026, with both proposed defaults taken.
Spec: `docs/spec/features/F18-full-era-refit.md`.

> Extends master spec v3.0 rather than implementing a row of it. The anchors are contracts
> the refit must not break; every fitted number underneath them is expected to move.

## Objective & spec anchors

`configs/physics_params.yaml` was fitted on seasons 2024–2025; the frozen A-09 snapshot
holds 2022–2025 and `configs/ingest.yaml:6` declares all of them. Reproduced exactly at
Bahrain, era 2024:

| Season scope | n_laps | t0_s | sigma_driver_s |
|---|---|---|---|
| 2024 + 2025 | 1958 | 98.597 | 0.5653 |
| **committed `physics_params.yaml`** | **1958** | **98.597** | **0.5653** |
| all 2022–2025 | 3705 | 99.465 | 0.6571 |

So `make fit` from the frozen snapshot does not reproduce the shipped physics: the
reproducibility pack does not round-trip, and the fitted layer uses half the data it has
for no stated reason. 2022 through 2025 are one regulation era — that is why they share an
`era` value.

Anchors, as invariants:

- **5.3.4 / E-09** — the cleaning contract. F18 adds the rule it is missing (below).
- **E-10** — the joint regression's identification discipline. The VIF gate re-runs on a larger sample; some circuits will change status.
- **E-12** — completeness. The new coverage gate is that idea applied one layer later.
- **E-14** — the frozen calibration split is untouched; `_refuse_validation_rounds` stays in the path.
- **T5** — degradation's `min_drivers`/`min_stints` gates see more data, so fewer circuits should need cluster transfer.
- **A-09** — the pack round-trips after this.
- **M1–M11** — every result regenerates; the headline may move in either direction.

**A second defect, found while testing feasibility.** The refit crashes on the third
circuit with `LinAlgError: SVD did not converge`, on austrian_grand_prix.
`fit_joint_pace`'s `clean` mask (`joint_pace.py:59-65`) requires green, accurate, a lap
time and no pit in/out — but not a **tyre age**, though `tyre_life` is a regressor in its
own design matrix. NULL ages become NaN columns and LAPACK raises.

178 laps repo-wide carry a known slick compound, pass every other clean rule, and have no
tyre age: 2022 Austrian 74 and Monaco 66, 2025 Belgian 17 and Australian 2, 2026 Barcelona
19. FastF1's `TyreLife` is patchy on older seasons (2.1% of all 2022 laps). The committed
physics is numerically clean — zero non-finite constants, verified — so this is a
robustness gap, not a corrupted artifact. But `validate_complete` tests `is None`, and a
NaN is not None, so it would have rendered `nan` straight into the yaml.

## Deliverables

**The fixes — these land first and are independently correct:**

- `senna/physics/fits/joint_pace.py` — add `tyre_life.notna()` to the `clean` mask in both `fit_joint_pace` and `age_partial_residuals`. A lap with no tyre age cannot enter a regression about tyre age.
- The per-season quality report — the exclusion counted and named, as every other 5.3.4 rule is.
- `senna/physics/fits/params_writer.py` — `validate_complete` refuses NaN and Inf as well as null; `validate_origins` added beside it.
- `senna/physics/fits/run.py` — season-coverage assertion beside `assert_quality_reports` (`:58`): refuse to write params unless the ingested seasons match `configs/ingest.yaml`'s declared list. This is the defect fix.
- **`.gitignore:26-34`** — the `models/explain/` re-includes are pinned to literal checkpoint names, so regenerated surrogates land **silently ignored** and a clean clone then cannot serve (`serve/loader.py:92` raises). Updated before `make explain` runs.
- `tests/env/fixtures/F16_physics_pinned.yaml` — a two-circuit extract of the pre-refit constants, for the golden test (decision 1).
- The stale Makefile comment calling `data/circuits/` gitignored (decision 2).

**The regeneration, in dependency order:**

- `configs/physics_params.yaml` — `make fit`
- `configs/transforms.yaml` **and the `c_lc`/`c_atk`/`p_der` block in `configs/physics_2026.yaml`** — `make synth` writes both
- `docs/synth/validation_summary.yaml`, `docs/synth/validation/*.png` — `make synth-figures`
- `models/headline/*`, `models/era2024/*`, `models/runs.json`, `models/abl-*` — `make headline`, `make ablate`, `make finetune`
- `models/explain/<new-version>/*` — `make explain`, both triplets
- `docs/results/F14/store/*.json` (19) — `make eval`
- `docs/results/F14-evaluation.md`, `figures/*.png` — `make report`
- `docs/results/F08-ablations.md`, `F09-explainability.md` — rewritten
- `INDEX.md` decisions log, `docs/freeze.md`, `docs/design-and-implementation.md` — the model names and headline numbers they quote

## Constants & configs

F18 introduces no physics constants — it regenerates them. Two gates:

| Name | Value | Origin | Home |
|---|---|---|---|
| `require_full_season_coverage` | `true` | **operational** — a correctness gate, not a tunable; sized by the defect it prevents | `configs/fits.yaml` |
| `require_finite_params` | `true` | **operational** — closes the NaN-is-not-None hole in `validate_complete` | `configs/fits.yaml` |

Every regenerated value keeps the provenance tag its fitter already emits. The
`physics_params.yaml` diff will be large and **is the evidence**: read two things out of it
before spending compute downstream — which circuits change E-10 identification status, and
which compounds stop needing T5 transfer. Both are reportable findings that belong in the
dissertation.

## Tests first

- **`test_refit_reproduces_the_committed_params`** — *slow, DB-backed.* The headline. `make fit` over the frozen snapshot renders byte-identically to the committed file. Red now, green after, red forever if anyone refits on partial data again.
- **`test_a_partial_ingest_refuses_to_write_params`** — an ingest missing a declared season raises rather than writing.
- **`test_laps_without_a_tyre_age_are_excluded`** — a frame carrying a NULL `tyre_life` on a slick lap does not reach the design matrix, and the count is reported. The crash, pinned.
- **`test_params_refuse_non_finite_values`** — a fit yielding NaN or Inf raises `IncompleteParamsError` instead of rendering `nan` into the yaml.
- **`test_every_era_2024_season_reaches_the_fit`** — asserted by season, not by count.
- **`test_params_still_render_deterministically`** — `params_writer`'s existing guarantee, re-checked on the new file.

The three tests that genuinely break: `tests/eval/test_freeze.py:31` and `:40` (both **CI
gates** via `make verify`), and `tests/env/test_engine_identity.py:215` (decision 1).
Roughly a dozen model-version string literals in hand-built fixtures go stale without
failing — updated for honesty, listed in the ship report.

## Edge cases handled

- **E-09** — the missing cleaning rule is added *as a cleaning rule*: excluded, counted, reported. Not a `nan_to_num` patch.
- **E-12** — the coverage gate.
- **E-14** — calibration rounds untouched; held-out data stays held out.
- **E-10** — VIF re-run on the larger sample; status changes reported, not hidden.
- **T5** — transfer fallbacks re-evaluated; fewer expected.
- **A-09** — round-trip restored and enforced by test.

## Acceptance checklist

- [ ] `make fit` over the frozen snapshot reproduces the committed `physics_params.yaml` byte-identically, enforced by test
- [ ] Laps without a tyre age are excluded, counted and reported
- [ ] Params refuse NaN/Inf and untagged origins
- [ ] A partial ingest refuses to write params
- [ ] `.gitignore` updated **before** `make explain`, and the new surrogate dirs are actually tracked
- [ ] The chain re-runs cleanly: fit → synth → headline/ablate/finetune → explain → eval → report
- [ ] New frozen triplet recorded in INDEX with fingerprint and gate values
- [ ] Fidelity badge re-measured, not carried over
- [ ] `docs/results/*` regenerated; old headline numbers retained beside the new ones
- [ ] `make verify` green; CI green on the merge
- [ ] Cold-cache `ruff` over the whole repo

## Out of scope

- Driver identity (F17) — depends on this.
- Any change to the physics *model*. F18 changes what data the existing fitters see, plus two robustness gates.
- Re-deciding the era boundary — `first_2026_season` is sourced and stays.
- **`make circuits`** — decision 2.
- `M2_CONFIG_FILES` (`coefficients.py:42`) and the harvest study (`sensitivity.py:158`) do not hash `physics_params`, so their `config_hash` will not move even though their results will. `test_freeze.py:66-77` recomputes from their own preimages, so it stays green. Their provenance will under-describe the change — recorded in the ship report, not fixed here.
- The spec's `data/synth/` deliverable is wrong; synth writes `configs/transforms.yaml` and `docs/synth/`. Corrected here.

## Decisions (Saad, 11 August 2026)

**1. The F16 golden test is pinned to a frozen physics extract.** Its fixtures are a
photograph of a race as it ran *before* the F16 extraction, which is what makes them proof
the extraction changed no behaviour. They are built through `F1RaceEnv`, which reads
`physics_params`, so every constant moving breaks them. Regenerating them at the post-refit
commit would make the test pass and destroy the evidence — it would then only prove the
engine agrees with itself today. Instead a small two-circuit extract of the pre-refit
constants is committed, and the golden test builds its scenario from that. F16's identity
claim survives every future refit, because it was only ever a claim about the engine tick.

**2. `make circuits` is skipped.** It reads no physics whatsoever yet rewrites 41 tracked
files (20 circuits x `ribbon.glb` + `meta.json`, plus `index.json`). Re-running it produces
a large binary diff that means nothing and hides the diff that does. Circuit geometry is a
function of track data, not fitted physics. The stale Makefile comment calling
`data/circuits/` gitignored is corrected in the same commit.

## Notes for the build

**There is no partial-landing path.** `make verify` runs in CI and executes both
freeze-chain tests, so CI goes red the moment `physics_params.yaml` lands and stays red
until the store, the chapter and both manifests are regenerated and committed together.
F18 lands as one branch, all-or-nothing.

**Fix, then refit, then regenerate — in that order.** The two fitter fixes and the
`.gitignore` change are correct on their own merits and should be committed before the
refit, so the refit's diff is purely data-driven. The `.gitignore` fix in particular must
precede `make explain` or the surrogates vanish silently.

**Read the fit diff before spending compute.** The chain is long and every stage reads the
previous one's artifacts, so a mistake at `fit` is only visible at `eval` hours later.

**The F14 headline will move and may get worse.** M1 was +2.08 places, CI [1.71, 2.48].
More data is better physics, not necessarily a better-looking result. Report whatever comes
out. Keep the previous headline model, fidelity badge and F14 numbers in INDEX beside the
new ones — "the physics improved and here is exactly what moved" is a stronger viva answer
than a clean slate, and far stronger than results whose constants cannot be reproduced from
their own data pack.

**Compute is not the constraint.** Ablations are 4M steps per arm, four arms, two seeds —
about an hour of env time at the measured throughput. The expensive part is artifact
management and the results rewrite.
