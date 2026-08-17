# SENNA — index

Claude: read this file at the start of every session. Update it exactly when the
workflow commands say to: plan approved -> Planned; end of /ship -> In review;
/land -> Done + date + lesson link. Keep "Active" and "Next up" true at all times.

**Active feature: F24 — tyre-model repair and headline retrain. Planned 17 Aug 2026**
(`docs/plans/F24-plan.md`). Root cause found live: 37 of 145 fitted deg curves are
bound-clipped to a=0.0 (the 2026 SOFT nearly everywhere), so tyres are free and the
policy learned pit-lap-2-then-never-stop — the mechanism behind the M9 miss. Repair
ladder: bound-clip detection -> pooled per-compound refit -> cross-era prior, plus a
no-free-tyres backstop in build_scenario. Then retrain the headline and re-run the
suite. Expect M1 to shrink; the pre-repair store archives for the comparison.

**Next up: F25 — the Streamlit ceiling, reached on purpose. Planned and approved
18 Aug 2026** (`docs/plans/F25-plan.md`): design system in theme.py, the s_track
track map with autoplay motion, auto-composed race headline and moments strip.
Builds on its own branch after F24 lands. app/ only — it cannot touch the frozen
chain.

F23 landed 15 Aug 2026. The dashboard is three tabs
(Strategy / Circuit / Analysis) with a section rail; all six spec views survive as
sections and every colour lives in `frontend/src/config/palette.ts`, sampled from the
reference screenshots Saad supplied on 11 Aug. Frontend only — no backend change, and no
number on screen that the API did not already serve.

**F23's lesson is that a green suite is not a working page.** 200 tests, two subagent
reviews and a clean gate all passed while the replay was 22 shapes going round a loop
with no figure beside them, the circuit was a two-pixel hairline, the tyre view drew a
flat surface for a fact a surface cannot show, and the reward decomposition never
rendered at all (cards number laps from 0, frames from 1, and the join was equality).
Every one of those was found by looking at a screenshot. The review battery did find the
two real logic defects — stints cut on compound change instead of `in_pit`, and `?run=`
written with `history.replaceState` where react-router never sees it — so both kinds of
check earned their place. Add a look-at-the-artefact step to any UI feature.

F17 landed 13 Aug 2026. `configs/drivers.yaml` now carries 31
era-2024 seats fitted over 2022-2025 and 22 era-2026 seats over the calibration rounds,
each with the laps and seasons behind it. Read them as **seat** effects, not skill: era
2024 pools four seasons of whatever car the driver was in, which is why the leaf is
`seat_pace_s`. `drivers=None` stays the default everywhere the project trains and
evaluates, the F16 golden fixtures replay byte-identical and `physics_params.yaml`
re-rendered byte-identical, so the frozen triplet is untouched. **M2 was re-measured**
(−3.66 → −4.58, sign test unchanged at 1W/8L/1T p=0.039) — see the decisions log.

**Two things F17 left on the table.** `tests/api/` has three `slow` tests failing on main
(`test_energy_series_covers_every_lap_within_the_store_bounds`,
`test_a_baseline_run_streams_card_null_laps_and_a_normal_complete`,
`test_a_replay_failure_fails_both_runs_and_clears_the_cache`), and the counterfactuals
module is flaky besides — a different test fails run to run. Verified pre-existing against
a main worktree during the F17 ship, so not F17's doing, but CI's fast suite does not run
them and the freeze runbook does not either. Worth a session before the tag. Second:
`configs/eval.yaml` `seeds_per_race: 5` now buys almost nothing for M2 (below), and cutting
it is a live decision rather than an oversight.
**Data-integrity defect found 11 Aug 2026, FIXED by F18 (Saad's call: refit on the full era):**
`configs/physics_params.yaml` was fitted with only seasons 2024–2025 reaching the pace
fits. Reproduced exactly at Bahrain era 2024 — committed `n_laps=1958, t0_s=98.597,
sigma_driver_s=0.5653` matches a 2024+2025 fit to every digit, while the full era gives
`3705 / 99.465 / 0.6571`. So `make fit` from the frozen snapshot did not reproduce the
shipped physics: the reproducibility pack did not round-trip.

**Corrected during the F18 build:** the first diagnosis said the 2022 and 2023 seasons had
not been ingested. They had. The pre-refit file's own watermark reads `seasons 2022-2026,
round 6` and it carries a `hazards` block for the French GP, raced only in 2022, with race
counts identical to the post-refit file. Every declared season was in the store; 2022 and
2023 reached hazards, pit loss and energy and reached no joint pace fit at all. The scope
was not unrecorded — it was recorded wrongly, which is the sharper finding. A season-level
gate would have passed that run silently, so F18 ships `assert_pace_season_coverage` at
the layer the defect happened, and the guard that actually failed on main is the
byte-identity round-trip test.

**What the refit changed, read out of the fit diff as the spec requires.** E-10
identification is **unchanged**: `canadian_grand_prix/2026` is the only identified
circuit-era before and after, so era 2024 still borrows 2026's pooled mass sensitivity and
the wider data did not resolve the fuel/evolution confound. T5 transfer is **unchanged in
kind**: 53 borrowed curves became 54, and no compound stopped needing the cluster
transfer. Both contradict the spec's expectation ("fewer circuits should fall back") and
are reported rather than dropped. What the wider data did buy is coverage: seven degradation
curves that did not exist before (Azerbaijan SOFT, Canada's full set, France HARD and
MEDIUM — circuits raced only in 2022–23), native curves 85 → 91, and circuits with native
era-2024 fits 23 → 25.

**Two physicality guards, found by refitting.** Austria's fuel VIF fell 131.7 → 22.5 on
the wider data and it became separable — returning a *negative* mass sensitivity. Unguarded
it would have become era 2024's only identified circuit and stamped −0.007421 onto every
other circuit in the era, inverting the 2026 mass transform for two thirds of
`transforms.yaml`. Identification now requires a positive estimate as well as a separable
design, and `pool_k_m` refuses a non-positive pool.
**Next up, after F23:** physics uncertainty (F19), then explanation language, then F20 the single
observation change (batched, because it invalidates the frozen triplet). F21 look-ahead and
F22 multi-agent are stretch, in that order. The roadmap comes from Saad's sixteen-point
architectural review (7 Aug 2026) and extends master spec v3.0 rather than implementing it —
**each feature needs a spec written before /plan-feature can read it**, and F19 has none
yet, so the next session starts by writing `docs/spec/features/F19-*.md`.
**Deferred:** the freeze (docs/freeze.md — tag v1.0.0, GitHub release with the snapshot
asset, CI green) now waits for the F16–F20 arc to settle; tagging v1.0.0 immediately
before restructuring the engine would freeze a build that is about to change. The demo
video and the written dissertation follow it. Open item, unchanged: the COMP702
submission mechanism (bundle vs repo access) decides where the snapshot travels.
**One version for the writing (Saad, 13 Aug 2026):** pick a freeze-for-writing version
soon, then make the design doc, the results chapter and the thesis all quote that same
version's numbers. M2 has already drifted once — F18's refit turned an inconclusive wash
into 1W/8L/1T at p=0.039 — and F17 moves it again by design, so the live risk is three
documents citing three different rolls. This does not block F17; it decides which
post-F17 state gets tagged.
**ANSWERED 14 Aug 2026 — the freeze-for-writing version is the one the repo already
ships:** headline `senna-ppo-5e3ddb15d584-C-01769472`, era-matched
`senna-ppo-39cabd466e03-C-03538944`. A full retrain on the post-F17 configs was run end to
end (3-seed slate, both surrogates, era-matched fine-tune, M1-M11, both sensitivity passes,
Chapter 7) and then **discarded on Saad's call**, because it reproduced the frozen triplet
exactly and would have renamed every artifact for no measurable gain. The evidence is worth
keeping even though the branch is not:

- all three seeds selected the same checkpoint at the same step — 101 at 1,130,496/6.355,
  211 at 4,227,072/6.295, 331 at 1,769,472/6.541667;
- `policy.pth` and the optimizer state are **byte-for-byte identical** for the headline and
  the era-matched model alike, so only wall-clock timestamps differ inside the archives;
- both surrogates reproduce their fidelity to sixteen decimal places (pit 0.9975926576056974,
  mode 0.9818947790761824; era-matched 0.9914987248087213 / 0.9824223633545032);
- 11 of 13 M1-M11 store payloads byte-identical, the other two differing only in an embedded
  `model_version` string, and Chapter 7's whole diff was two version strings and a commit hash.

Two things follow. **F17 is confirmed inert on the default training path** by a third
independent route, after the F16 golden fixtures and the byte-identical
`physics_params.yaml`. And **a retrain cannot move any number in this repo unless something
that affects learning changes** — the fingerprint drifted only because F17 added a
`driver_identity` block to `configs/fits.yaml`, which sits in `train.CONFIG_FILES` and which
training never reads. If a different result is ever wanted, the levers are new seeds, a
changed reward or curriculum gate, or different physics; not a rerun.

## Feature ledger

| ID | Feature | Depends on | Status | Branch | Lesson |
|----|---------|-----------|--------|--------|--------|
| F00 | Repo skeleton, CI & spec split | — | Done 14 Jul 2026 | feature/F00-repo-skeleton | [F00](docs/learn/F00-repo-skeleton.md) |
| F01 | Data ingestion & quality reports | F00 | Done 15 Jul 2026 | feature/F01-data-ingest | [F01](docs/learn/F01-data-ingest.md) |
| F02 | Physics model fits | F01 | Done 16 Jul 2026 | feature/F02-physics-fits | [F02](docs/learn/F02-physics-fits.md) |
| F03 | Synthetic 2026 generator (T1–T8) | F02 | Done 17 Jul 2026 | feature/F03-synthetic-2026 | [F03](docs/learn/F03-synthetic-2026.md) |
| F04 | Circuit ribbon pipeline | F01 | Done 17 Jul 2026 | feature/F04-circuit-ribbons | [F04](docs/learn/F04-circuit-ribbons.md) |
| F05 | F1RaceEnv: obs, masks, dynamics, reward | F02, F03 | Done 19 Jul 2026 | feature/F05-race-env | [F05](docs/learn/F05-race-env.md) |
| F06 | Rivals, baselines, oracle & throughput | F05 | Done 19 Jul 2026 | feature/F06-rivals-baselines | [F06](docs/learn/F06-rivals-baselines.md) |
| F07 | Training: MaskablePPO + curriculum | F05, F06 | Done 19 Jul 2026 | feature/F07-training | [F07](docs/learn/F07-training.md) |
| F08 | Ablations & headline runs | F07 | Done 19 Jul 2026 | feature/F08-ablations | [F08](docs/learn/F08-ablations.md) |
| F09 | Explainability: surrogate, SHAP, cards | F07 | Done 21 Jul 2026 | feature/F09-explainability | [F09](docs/learn/F09-explainability.md) |
| F10 | Backend: API, worker, WS, deploy skeleton | F07, F09 | Done 22 Jul 2026 | feature/F10-backend-serving | [F10](docs/learn/F10-backend-serving.md) |
| F11 | Frontend shell + Views 1–2 | F04, F10 | Done 23 Jul 2026 | feature/F11-frontend-views-1-2 | [F11](docs/learn/F11-frontend-views-1-2.md) |
| F12 | Views 3–4: Energy, Tyre Surface | F11 | Done 24 Jul 2026 | feature/F12-views-energy-tyre | [F12](docs/learn/F12-views-energy-tyre.md) |
| F13 | Views 5–6: Live, Counterfactual | F11 | Done 25 Jul 2026 | feature/F13-views-live-counterfactual | [F13](docs/learn/F13-views-live-counterfactual.md) |
| F14 | Evaluation suite M1–M11 + counterfactuals | F08, F09 | Done 28 Jul 2026 | feature/F14-evaluation | [F14](docs/learn/F14-evaluation.md) |
| F15 | Demo, docs, reproducibility pack & freeze | F10–F14 | Done 29 Jul 2026 | feature/F15-demo-freeze | [F15](docs/learn/F15-demo-freeze.md) |
| F16 | Race engine extraction | F05, F06 | Done 8 Aug 2026 | feature/F16-engine-extraction | [F16](docs/learn/F16-engine-extraction.md) |
| F17 | Driver identity | F02, F16, F18 | Done 13 Aug 2026 | feature/F17-driver-identity | [F17](docs/learn/F17-driver-identity.md) |
| F18 | Full-era refit and revalidation | F02, F16 | Done 12 Aug 2026 | feature/F18-full-era-refit | [F18](docs/learn/F18-full-era-refit.md) |
| F23 | Dashboard restructure and visual language | F11, F12, F13 | Done 15 Aug 2026 | feature/F23-ui-revamp | [F23](docs/learn/F23-ui-revamp.md) |

Statuses: Todo -> Planned -> In review -> Done. Shipping happens inside one session, so
there is no persistent "building" state; if a session dies mid-/ship, the branch holds
the work — resume with `claude --continue`, or start fresh and say
"resume F0x from its branch".

## Decisions log (spec Part 7 answers)
- **OQ-1 name:** SENNA (Saad, 7 Jul 2026). Repo, docs and UI say SENNA; code identifiers
  follow the spec.
- **OQ-2 compute:** MEASURED 19 Jul 2026 (F06 `make bench`, spec 5.6.2): **18,477 env
  steps/s aggregate** (~1,540/worker across 12 SubprocVecEnv workers) on Saad's Mac
  (macOS arm64 / Apple Silicon, 10 cores), random-legal actions with the per-step mask
  fetch on the clock. That puts the 8M-step budget at ~7 minutes and 15M at ~14 —
  comfortably above the ~300 steps/s floor and even the spec's 1,000–4,000 expectation,
  so training is cheap and the F07 3-seed + ablation plans are safe as written. Config
  hash e28c3d83ba10. A GPU is optional (the policy is tiny); note the real training
  hardware here if it differs.
- **OQ-3 deadline & AI policy:** default freeze 17 Nov 2026; AI assistance declared.
  Saad: replace with the real submission date and the written COMP702 policy.
- **OQ-4 … OQ-12:** spec defaults apply until edited here.
- **F06 rival bands (Saad, 19 Jul 2026):** held-out test band extrapolates toward each
  archetype's character; F14 must also run the fixed scripted baselines against the
  test band and frame the result as robustness, not in-distribution generalisation.
  TO-DO before F14's M1 run: sanity-check the stylised rival bands against the real
  ingested pit-lap distributions — M1's headline is provisional until that passes.
- **Paired evaluation pairs on event traces, not raw seeds (19 Jul 2026):** tyre-failure
  and pit-service draws consume RNG variates policy-dependently, so same-seed episodes
  diverge in events after the first different stop; F06's EventTrace is the mechanism,
  F14's M1/A-06 harness must use it.
- **Unfitted-compound mask guard — MUST LAND BEFORE F08's headline runs (F07 ship,
  19 Jul 2026):** the action mask does not forbid pitting onto a compound the circuit
  has no deg fit for; unfitted slicks fall back to identity grip (no wear until the
  cliff), so a training agent can learn e.g. "SOFT at Suzuka never degrades". Fix =
  mask slicks outside scenario.available_compounds. Touches the F05 mask contract
  (F-16), so it opens F08's plan rather than landing as a hotfix. F07's own gates are
  unaffected (Stage A runs Monza solo; the heuristic now shops fitted compounds only).
- **F08 headline model (11 Aug 2026, F18 refit):** `senna-ppo-5e3ddb15d584-C-01769472`
  (seed 331, step 1,769,472, 6.542 validation points) promoted to `models/headline/` —
  the frozen checkpoint F09 explains and F10 serves. Era-matched:
  `senna-ppo-39cabd466e03-C-03538944` (5.550 on the 2024 banks). Superseded:
  `senna-ppo-6b6edb78d84e-C-00835584` at 6.517, and `senna-ppo-db031aead155-C-02211840`.
  Evidence: docs/results/F08-ablations.md; ledger models/runs.json. W&B offline.
  **The slate was trained twice** under two fingerprints and every one of the eleven
  runs came back identical to the last float digit — the project's strongest
  determinism evidence, and unplanned.
- **F09 fidelity badge (11 Aug 2026, re-measured):** the surrogate explaining the
  headline agrees on **99.76%** of held-out pit decisions and **98.19%** of energy-mode
  decisions, gate 0.90 (spec 5.8.2); both mean KLs roughly halved. Gradient cross-check:
  mean Spearman **0.548** over 500 decisions, all positive, minimum 0.222. 14,460 cards
  across 240 validation races. The era-matched surrogate improved on every measure
  (99.15% / 98.24%). Previous badge: 99.70% / 99.08%, cross-check 0.687. Evidence:
  docs/results/F09-explainability.md. A retrain invalidates all of it by construction
  (E-15) — `make explain` must re-run before F10 serves a new checkpoint.
- **Railway deploy deferred (Saad, 22 Jul 2026):** 5.11.1's public deploy is not
  executed. The dissertation deliverable is a reproducible codebase plus the
  presentation video, so `docker compose up --build` is the supported target — a
  marker can run the full stack from a clean clone, which is why the frozen triplet,
  surrogate and ribbons are committed. The serving layer stays deployment-ready
  (Dockerfile.api, start scripts, migrate-on-start, docs/deploy.md) but that runbook
  is now unverified in production and says so. Revisit only if a live URL is wanted
  before the viva.
- **F10 spec divergences (22 Jul 2026):** seven deliberate, recorded with their
  resolutions in docs/plans/F10-plan.md ("Flagged spec divergences") — the E-15 cache
  key gains a scenario digest (the literal 5.9.3 key collides circuits), rival_band
  passed explicitly, frames in a lap_frames JSONB table, era-2024 fields 20 cars,
  cards ride sim:lap (no agent:decision event), local WS is ws://localhost:8000/ws
  (no /ws proxy), one Dockerfile with two start commands. Also new: the fourth
  provenance origin `operational` (configs/README.md) for stated engineering defaults.
- **Full ribbon library before the video (Saad, 22 Jul 2026):** after F11, run
  `make circuits` across all ingested events and commit the GLBs (~100 KB each,
  ~2.6 MB total) so the demo and a clean clone show the whole circuit library, not 3
  circuits. Recorded in docs/plans/F11-plan.md decisions.
- **AR-10 race fuel (spec Part 8):** VERIFIED 16 Jul 2026 — the FIA 2026 regs cap fuel
  energy flow at 3,000 MJ/h (energy-based, replacing 100 kg/h) and the race allowance
  works out to ~70 kg with the Advanced Sustainable Fuel spec. Sources: Formula1.com
  2026 regulation explainers; FIA 2026 Technical Regulations issue 8 (24 Jun 2024).
  The assumption stands as written ("about 70 kg, energy-flow limited"); next fits
  session may lift the grade-C flag per the register's close-out rule.

- **F14 era-matched fine-tune (11 Aug 2026, refit):** `senna-ppo-39cabd466e03-C-03538944`
  (seed 331, warm-started from the headline, 2M Stage C steps on the 2024 constants)
  promoted to `models/era2024/`, scoring **5.550** mean points on the 2024 validation
  banks. It measures the F-24 regulation confound: a 2026-physics agent scored on 2024
  races loses points to the car, not to its strategy. Superseded:
  `senna-ppo-db031aead155-C-02211840` at 6.336 against the old headline's 3.802 on the
  two-season physics — the pair moves together, so the gap is the quantity to quote, not
  either figure alone. Its surrogate is now fitted and committed
  (`models/explain/senna-ppo-39cabd466e03-C-03538944/`), so the `pending-F14` note the
  serving flip used to carry no longer applies (Saad's decision 3 named the flip the
  designated cut).
- **F14 headline results (11 Aug 2026, re-measured on the full-era physics):** M1
  **+2.279 places** over 480 paired seeds, CI [1.913, 2.663] — met, and better than the
  two-season result. M10 clean over 480 races. M3 regret fell (median 33.09 → 30.48 s,
  mean 86.98 → 71.78 s). Missed: M2, M4 (0.704 against a 0.912 ceiling, derates 0.097),
  M5, M6 (0.213 of 517 stops), M8 (0/5 circuits), M9 (**37.92 tyre failures per 100
  races**). M7 diversity nearly tripled, 0.226 → 0.653 nats. M11 luck share **0.786**
  CI [0.70, 0.86]. Read M1 with M9: the agent still buys track position by over-running
  tyres, and the refit did not touch that. Evidence: docs/results/F14-evaluation.md.
  Previous: M1 +2.083 CI [1.71, 2.48], M4 0.649, M6 0.228, M9 37.29, M11 0.758.
- **M2 re-measured with named drivers (F17, 13 Aug 2026).** `eval/traces.py` filled each
  seat's pace from `rng.normal` while holding a list keyed by real driver codes; it now
  carries the seat effect the joint regression measured for that driver at that
  circuit-era. Mean delta **−3.66 → −4.58**, CI [−5.82, −1.16] → **[−8.38, −1.20]**. The
  pre-registered sign test is **unchanged at 1W/8L/1T, p=0.039**, so the adverse conclusion
  stands and only its size moved. The direction was not knowable before the roll and the
  plan said so in advance: the seat offset largely cancels inside each pair (both legs
  share the lineup, and the counterfactualled driver is car 0 in both), so what moves is
  field context. Las Vegas swings furthest — a fitted Verstappen seat puts the replay
  baseline on the front row. **Read M2's spread with care from here on:** a twin replay is
  near-deterministic (zero lap noise, fitted pit service, events from the trace), so the
  five seeds per race were only ever varying the driver draw, and nine of ten races are now
  identical across all five. `seeds_per_race` stays at 5 — changing a published metric's
  shape is a separate decision. Evidence: docs/results/F14-evaluation.md.
- **Two F14 rows moved in ways worth arguing about (11 Aug 2026).** **M2 got worse and
  became significant:** 4W/5L/1T at p=1.000 (mean −0.60) became **1W/8L/1T at p=0.039**
  (mean −3.66; F17 later re-measured this to −4.58, above). The pre-registered sign test
  rejects in the adverse direction, so
  the old reading — "competitive with elite humans, not better" — is no longer
  supportable. Better physics turned an inconclusive wash into a measured gap, which is
  the more useful finding and belongs in the limitations section. Read it with the 25
  snapped stops the replay baseline needed and with M8. **M5's VSC blindness partly
  lifted:** recall 0.000 → **0.085 at precision 1.000** — ten calls, none wrong, where
  the old chapter reported zero across 311 windows. SC precision fell 0.942 → 0.820 as
  recall rose 0.308 → 0.401.
- **DB-wipe guard (F14, 28 Jul 2026):** `senna/data/db.py::require_disposable` refuses to
  drop tables on any database not named `*_test`, resolving the name the way the driver
  does (a `?database=` query parameter overrides the URL path, which was a live bypass).
  All three destructive test modules call it, CI's ephemeral Postgres is renamed
  `senna_test`, and compose provisions it on first boot. The escape hatch names the
  database out loud (`SENNA_ALLOW_DESTRUCTIVE_DB=senna`) so it cannot be left armed.
  Closes the recurring wipe hazard — the store was lost three times, twice in one session.
- **E-02 harvest cap MEASURED (F14, 28 Jul 2026):** under the FIA's refined 7 MJ cap
  (Issue 18 Art C5.2.10) the frozen agent loses **0.13 places** and its derate share goes
  **0.078 -> 0.182**. It keeps its results and runs out of energy more than twice as
  often. This is the frozen agent's robustness, NOT a model re-optimised for 7 MJ.
  circuits.yaml stays at 8.5 with a header explaining why; AR-05 carries the verification.
  Reproduce with `make sensitivity`.
- **AR-04 energy store (spec Part 8):** VERIFIED 24 Jul 2026 — official FIA regulation
  text. FIA 2026 Formula 1 Technical Regulations Issue 8 (24 Jun 2024), Art 5.4.9: "The
  difference between the maximum and the minimum state of charge of the ES may not
  exceed 4MJ at any time the car is on the track" — unchanged in the consolidated 2026
  Section C Issue 18 (7 May 2026) as Art C5.2.9. The rule is continuous in substance
  since 2014, though the 2025 regs carry it in the Art 5.3.2 energy-flow diagram, not
  prose (the register's "Art 5.4" pointer resolves to 5.4.9 in the 2026 issue the spec
  cites). Precision for the viva: the regs regulate a max–min delta SoC, not "usable
  capacity" — total cell energy is unregulated and larger — so SOC in [0, 4] models the
  regulated window exactly. Bonus: the 2014–2025 "max 4MJ/lap from ES to MGUK" diagram
  label is absent from the 2026 text, which is primary-source confirmation of F-02.
  The configs/physics_2026.yaml usable_capacity_mj comment now cites Art 5.4.9 / C5.2.9
  (done in F12, 24 Jul 2026).
- **Harvest-cap refinement to re-check before F14 (found during AR-04, 24 Jul 2026):**
  the FIA's 20 Apr 2026 refinements cut maximum permitted recharge from 8 MJ to 7 MJ
  (Issue 18 Art C5.2.10; floor of 5 MJ in qualifying; +0.5 MJ Manual Override under
  B7.2). Every circuits.yaml h_max_mj is still the 8.5 default — exactly the E-02 case.
  Re-verify per-event values against C5.2.10 before F14's headline runs.

## Timeline anchor (spec Part 6.2, start 8 Jul 2026)
F00 by 11 Jul · F01 by 21 Jul · F02–F04 by 4 Aug · F05–F06 by 25 Aug ·
F07–F08 by 15 Sep · F09 by 22 Sep · F10 by 6 Oct · F11–F13 by 3 Nov · F14–F15 by 17 Nov.
Falling behind? The cut order is spec Part 6.3 — and never cut action masking, the
cleaning contract, the calibration/validation split, the metric suite, or decision cards.

---

# Saad's operating manual

## One feature, start to finish
1. Open a terminal in the repo and run `claude`. Name the session after the feature
   (`/rename F05 race env` if your version supports it; otherwise the first message
   names it well enough).
2. Press Shift+Tab until the input bar shows **plan mode**, then type
   `/plan-feature F05`.
3. Read the plan. Ask about anything unclear — in plain English. Request changes the
   same way. When happy, say **approved** and accept when Claude Code asks to exit
   plan mode.
4. Type `/ship F05`. Claude branches, writes failing tests, builds, gets reviewed by
   the subagents, fixes the findings, writes your lesson, and stops with a ship report.
5. Read the ship report and the new lesson in `docs/learn/`. Run the "try it" commands
   yourself. Ask questions — this is your study time. Request changes if you want them.
6. Type `/land F05` when you are happy. Typing it **is** your approval — you do not have
   to say the word first. Claude merges to main, deletes the branch, and updates this
   file. If you are not happy, just say so instead; nothing merges until you land it.
7. Close the session. Next feature = fresh session. Run `/status` any time you are lost.

## When things wobble
- Context bloated, Claude repeating itself -> `/compact`, or land what is done and
  re-plan the remainder as a follow-up feature.
- Session died mid-build -> `claude --continue`, or a new session with
  "resume F0x from branch feature/F0x-...".
- Tests keep failing -> "re-read the spec anchors for this feature, then explain the
  failure before touching the fix".
- Claude typed a raw number into code -> "move that to configs with a provenance
  comment" (the spec-auditor should have caught it; say so).
- You disagree with a review finding -> you outrank the agents. Tell Claude to record
  the rejection with a one-line reason and move on.
- Claude wants to `git push` -> pushes are deliberately not pre-approved in
  `.claude/settings.json`; approve them when asked.

## What only you can do
Approve plans. Approve ships. Answer the VERIFY items (AR-10 fuel mass, AR-11 fastest
lap — spec Part 8). Put your real OQ-2 hardware and OQ-3 deadline in the decisions log
above. Read your lessons. Everything else is a command.
