# SENNA — design and implementation

A Formula 1 race-strategy engine for the 2026 regulations: a lap-level simulator, a
masked reinforcement-learning agent, a SHAP explanation layer, a six-view dashboard,
and an eleven-metric evaluation suite that reproduces from a clean clone.

Code frozen at commit `79c4434`, 29 July 2026. The `v1.0.0` tag and its release are the
one remaining freeze step (`docs/freeze.md`). MSc dissertation, COMP702, University of
Liverpool.

---

## 0. About this document

This is the design and implementation record for the whole system: what was built,
what each decision rejected, and where the evidence for every claim lives. It is
written to feed the dissertation's design and implementation chapters, and to let a
reader who has never seen the repository understand why the code looks the way it does.

Three conventions run through it.

**Every claim points somewhere.** Design decisions cite the file that implements them;
numbers cite the artifact that produced them. Where a figure appears in prose it can be
found in `configs/`, `docs/results/`, or a named module. Nothing here is asserted from
memory.

**Identifiers are the shared vocabulary.** The master specification (v3.0, 7 July 2026,
`docs/spec/source/`) assigns identifiers to its findings and decisions, and the code
cites them in comments: `F-xx` audit findings, `E-xx` edge cases, `R-xx` removals from
the previous design, `A-xx` additions, `T1`–`T8` synthetic-data transformations,
`M1`–`M11` evaluation metrics, `AR-xx` assumptions, `OQ-xx` open questions. Appendix A
glosses the ones that recur. A reader can grep any of them and land on the code that
honours it.

**The failures are in here too.** Six of the eleven evaluation metrics missed their
targets, one physics validation failed outright, and several designs were replaced
after they shipped. Those outcomes are reported in the same voice as the successes,
with their causes, because a system that only documents its wins has documented
nothing an examiner can check.

---

## 1. The problem

### 1.1 Race strategy as a decision problem

A Formula 1 race is a sequential decision problem under uncertainty with a small action
space and a brutal credit-assignment horizon. Once per lap a strategist chooses whether
to pit and onto which tyre, and how to spend the car's electrical energy. Roughly sixty
such decisions decide a result, the reward arrives once at the flag, and the state that
matters — tyre condition, fuel load, energy in the store, the gaps to the cars around —
evolves under events nobody controls: safety cars, rain, failures, other teams' stops.

That shape suits reinforcement learning. It also suits it badly in one specific way:
the outcome is dominated by luck. Quantifying that turned out to be one of this
project's more interesting results (§6.4).

### 1.2 Why the 2026 regulations

The 2026 Formula 1 technical regulations change the strategic problem more than any
ruleset since 2014, and they are widely misreported. The three facts that matter:

- **The MGU-K delivers 350 kW**, roughly triple the previous era's 120 kW, with power
  held flat to 290 km/h and tapering to zero at 355 km/h. The 400 kW figure that
  circulates is the internal combustion engine.
- **The energy store is a 4 MJ state-of-charge window**, not an 8 MJ battery. The
  regulation constrains the difference between maximum and minimum state of charge
  (FIA 2026 Technical Regulations Art 5.4.9, carried into the consolidated Section C
  as Art C5.2.9), which is a window rather than a capacity.
- **There is no per-lap deployment cap.** The 2014–2025 regulations capped energy from
  the store to the MGU-K at 4 MJ per lap; the 2026 text does not carry that limit. The
  era is *recovery*-limited instead, through a per-circuit harvest ceiling.

That last point is the one that reshapes strategy. When deployment is capped, energy
management is a scheduling problem inside a fixed budget. When recovery is capped and
deployment is not, energy becomes a stock the driver can spend down and must earn back,
and lifting to harvest costs lap time now to buy lap time later. An agent that can price
that trade is doing something a 2024-era agent never had to.

An earlier version of this project's own specification had these facts wrong — it
carried the 4 MJ/lap cap, an 8 MJ store and 400 kW as the electric figure. The v3
specification is the corrected one, and the corrections are the reason several
subsystems look the way they do (§2.2).

### 1.3 What was built

Ten subsystems, sixteen delivered features, one frozen codebase:

| Layer | What it does |
|---|---|
| Data | Ingests 2022–2026 F1 sessions from FastF1/Jolpica and OpenF1 into Postgres under a cleaning contract |
| Physics fits | Fits tyre degradation, pace, fuel, hazards, pit loss and energy integrals per circuit and era |
| Circuits | Builds a 3D track ribbon per circuit from GPS telemetry |
| Synthetic 2026 | Ages the fitted 2024 physics forward to 2026 through eight named transformations, then validates out of sample |
| Environment | A 22-car, lap-level Gymnasium environment with action masks and a three-term reward |
| Opponents | Three drawn rival archetypes, three scripted baselines, and a dynamic-programming oracle |
| Training | MaskablePPO through a competence-gated curriculum, plus four ablation arms |
| Explainability | Distilled surrogates, TreeSHAP attributions, counterfactual flip probes and decision cards |
| Serving + UI | FastAPI, an RQ worker, a WebSocket playback clock, and a six-view React/R3F dashboard |
| Evaluation | Eleven metrics on held-out ground, era-matched counterfactuals, and a reproducible report |

Roughly 16,200 lines of Python across the package, API and worker; 7,900 lines of
TypeScript in the frontend; 12,400 lines of tests; 4,400 lines of annotated
configuration; 17,000 lines of documentation.

### 1.4 The claims

Four things this system does that a template project would not:

1. **Corrected 2026 physics, from primary sources**, with the corrections traceable to
   the audit that found them.
2. **Regulatory compliance by construction** — illegal actions are masked out of the
   policy's distribution rather than penalised in reward, which turns compliance from a
   convergence property into an architectural one, measured at zero violations across
   480 evaluation races.
3. **Sim-to-real validation of the synthetic layer** against held-out real 2026 rounds,
   under a split frozen before any fit existed — which is how the synthetic layer's
   failure became a measurable result rather than an unexamined assumption.
4. **A variance decomposition** separating what the event draw explains from what the
   decisions explain: 75.8% of finishing-position variance is the draw, a conservative
   lower bound.

---

## 2. Requirements and constraints

### 2.1 The specification as contract

The master specification is treated as a contract rather than a starting point. Its
Part 5 was split into one markdown file per section under `docs/spec/` so a working
session loads only what it needs; Parts 1, 3 and 4 stay in the source PDF and are cited
by identifier. Where a feature specification and the master specification disagree, the
master wins and the disagreement is recorded in the feature's plan rather than
silently resolved. Around thirty such divergences and interpretation flags are recorded
across the sixteen plans; Appendix D lists the ones that shaped the architecture.

The specification also carries an audit of the project's earlier design — thirty
findings (`F-01`–`F-30`), twelve removals (`R-01`–`R-12`) and twelve additions
(`A-01`–`A-12`). Those identifiers are not decoration. `R-04` (the Ergast API shut down)
is enforced by a test that greps every tracked file under the code directories for the
dead service's name — documentation is deliberately out of scope, because the
specification itself names it. `F-25` (SHAP cannot be run directly on the policy network) is enforced
by a function signature that only accepts a tree booster. The audit is executable.

### 2.2 The interpretability contract

The project's one non-negotiable requirement, stated in the specification's Part 0.4 and
in the repository's root `CLAUDE.md`: **an inline constant in code is a defect.** Every
number lives in `configs/*.yaml` with a comment naming its origin, and there are exactly
four legal origins:

- **sourced** — a document backs it; the comment cites the assumptions-register row
  (`AR-xx`) or the specification section.
- **fitted** — a calibration notebook produced it; the comment names the notebook.
- **stylised** — an explicit presentation choice; the comment says so and the UI labels
  it on screen.
- **operational** — an engineering default (a timeout, a page size, a poll cadence);
  the comment states its sizing rationale. This fourth origin was added during the
  serving feature rather than stretching "stylised" to cover a 600-second job timeout.

Twenty-one configuration files carry 4,400 lines under this rule. The generated fits
artifact alone (`configs/physics_params.yaml`) is 2,267 lines holding 1,765 leaf values,
each with a per-line origin comment; 1,763 of them name the notebook that produced the
value, and the other two are the artifact's own data watermark and random seed. A null means
"fit me": `senna/config.py` raises `NullConstantError` rather than letting a placeholder
flow into a simulation.

The contract's real test is not whether numbers live in yaml. It is whether an examiner
pointing at any number on screen can reach its origin in one step. That is why the
frontend carries the same rule (`frontend/src/config/constants.ts` tags every value with
the same four origins), why the dashboard's dev overlay traces every displayed figure
back to the API response that produced it, and why stylised visuals — the interpolated
car motion, the exaggerated elevation, the tyre-temperature axis — say so in words on
screen rather than in a comment nobody reads.

### 2.3 Hard constraints

| Constraint | Consequence |
|---|---|
| One student, one laptop | Compute budgets are priced from a measured benchmark, not assumed (§5.5) |
| Free data only | FastF1/Jolpica plus OpenF1's historical tier; throttled, cached, resumable |
| No live timing | The product is a simulator and a replay system; the live view says so on screen (`R-05`) |
| Trademark exposure | Invented team colours, three-letter driver codes from the data, no sponsor marks, an unofficial-project footer everywhere public (`F-29`, `R-07`) |
| Academic integrity | AI assistance declared per COMP702 policy; the dissertation prose is the author's own |

### 2.4 The 2026 physics table

These are the regression tests of the whole project. A wrong value here fails the viva
regardless of how good the engineering is, so the root `CLAUDE.md` carries the full
table and every subsystem is checked against it. The load-bearing rows:

| Fact | Correct | Never |
|---|---|---|
| MGU-K electric power | 350 kW, flat to 290 km/h, zero at 355 | 400 kW (that is the ICE) |
| Energy store | 4 MJ usable window, SOC in [0, 4] | 8 MJ anywhere |
| Per-lap deployment cap | Does not exist | Any "4 MJ/lap" cap, plane, penalty or metric |
| Harvest cap | Per-circuit config, 8.5 MJ baseline | A hard-coded literal |
| Overtaking aid | Manual Override: gap ≤ 1.0 s, 350 kW to 337 km/h | DRS |
| Grid | 22 cars, 11 teams | 20 or 24 hard-coded |
| Fastest-lap point | Abolished from 2025 | Any fastest-lap action or reward |
| Compliance | Action masks plus physics clipping | Reward penalties for legality |
| Reward | Exactly three terms | Any extra term |

---

## 3. Architecture

### 3.1 The pipeline

The system is a directed pipeline with one loop back for evaluation. Each stage's output
is an artifact on disk, which is what makes any stage re-runnable without the ones
before it.

```
FastF1/Jolpica ─┐
                ├─► ingest ──► Postgres ──┬─► physics fits ──► physics_params.yaml ─┐
OpenF1 ─────────┘                         │                                          │
                                          ├─► circuit ribbons ──► data/circuits/*.glb │
                                          │                                          │
                                          └─► synthetic 2026 ──► transforms.yaml ◄────┤
                                                                        │             │
                                                                        ▼             │
                                                        F1RaceEnv (22 cars, 1 dec/lap)│
                                                                        │             │
                                    ┌───────────────────────────────────┤             │
                                    ▼                                   ▼             │
                          MaskablePPO curriculum              rivals / baselines /    │
                                    │                              oracle             │
                                    ▼                                                 │
                          frozen triplet ──► SHAP surrogate ──► decision cards        │
                                    │                │                                │
                                    ▼                ▼                                │
                            FastAPI + RQ worker + WebSocket ──► React/R3F dashboard   │
                                    │                                                 │
                                    └──────────► evaluation suite (M1–M11) ───────────┘
                                                          │
                                                          ▼
                                            committed store ──► make report
```

Three properties of this shape are load-bearing.

**Artifacts, not memory.** Every arrow crossing a stage boundary is a file: a yaml of
constants, a model triplet, a GLB mesh, a JSON store row. A stage can be re-run in
isolation and its output diffed. This is what makes `make report` a pure function of the
repository — it reads only the committed store, never a model or a database.

**One direction, one exception.** The evaluation suite is the only stage that reads
back into the middle of the pipeline: it loads the frozen model, rolls it in the
environment, and reads the synthetic layer's own validation summary for the sim-to-real
metric. Nothing else loops.

**Provenance travels with the data.** A model version string embeds the hash of the
eleven configuration files the run was reproducible from (`senna-ppo-<hash12>-<stage>-<step>`);
an evaluation store row carries that version, the config hash, the seed-manifest
fingerprint and the git commit. The chain is checkable from a clone, and `make verify`
checks it.

### 3.2 Runtime topology

Serving is five processes, and the split between them is a design decision rather than
an operational convenience.

```
browser ──HTTP/WS──► api (FastAPI, uvicorn)
                       │  validates, records, enqueues — never simulates
                       ├──► postgres  (runs, lap frames, decision cards, ingested data)
                       └──► redis     (RQ queue, result cache, pub/sub)
                                │
                              worker (rq SimpleWorker)
                                │  runs whole races with the frozen triplet,
                                └──► postgres (frames + cards, one transaction)
```

FastAPI runs every request handler and every open WebSocket on one asyncio event loop.
A 70-lap simulation inside a handler would freeze every connected stream and the health
endpoint with it, so simulations run in the RQ worker and never in the request path
(`F-26`). Even yaml reads leave the loop through `run_in_threadpool`.

The WebSocket is not a live feed. The worker persists the whole race in one transaction
before any client connects; the socket is a playback clock over stored rows (`E-16`).
That makes pause, scrub and reconnect ordinary reads — a seek is a list index move, and
a dropped connection needs no recovery because the next socket replays from the same
store.

The worker runs RQ's `SimpleWorker` rather than the default forking worker. The default
forks a work horse per job, which discards the model cache and re-imports torch for
every race; one process, loaded once, is the right shape for a serving worker whose
crash isolation belongs to the platform's restart policy.

### 3.3 Artifact classes

Three kinds of artifact, three different disciplines:

**Configuration** (`configs/*.yaml`, committed) — every constant with provenance. Some
are hand-written and sourced; some are generated by a fitting battery and byte-
deterministic, so `git diff` after `make fit` is the change detector.

**Models** (`models/`, mostly gitignored) — the frozen triplet is weights plus
VecNormalize statistics plus a manifest, saved as one unit with both artifacts' SHA-256
stamped into the manifest before the directory is swapped in (`F-23`). Weights without
their normalisation statistics receive raw observations where they expect z-scores, and
nothing throws — the triplet exists so that failure cannot happen silently. The
promoted headline, the era-matched fine-tune and both SHAP surrogates are committed
despite the gitignore, because a clean clone must be able to serve the demo.

**Evidence stores** (`docs/results/*/store/*.json`, committed) — one JSON per metric,
sorted keys, fixed indent, no timestamps anywhere, each wrapped in a provenance
envelope. A rerun that changed nothing produces identical bytes, which is what makes
"deterministic given the run store" checkable rather than asserted.

---

## 4. Cross-cutting design principles

Seven ideas recur across every subsystem. They are the intellectual spine of the
project, and most of them were learned the hard way.

### 4.1 Structural guarantees over learned ones

Wherever a property can be made impossible to violate, it is, rather than being
discouraged after the fact.

The clearest case is regulatory compliance. The earlier design penalised illegal actions
in the reward. That only discourages them in expectation after training converges, so
early in training and on rare states illegal actions still execute — and no compliance
percentage can ever be claimed, only measured. SENNA masks them: `MaskablePPO` applies
the mask inside the action distribution, so an illegal action has probability zero in
both rollout and update. Compliance moves from a hope to a property of the architecture.
The measured result is 0 coerced actions across 480 evaluation races.

The same instinct recurs: the reserved test seed bank is not "documented as off-limits",
it is behind a loader that refuses every caller but the evaluation feature; the training
environment cannot select the held-out rival band because the constructor raises; the
database wipe guard refuses any database not named `*_test`, resolving the name the way
the driver does because a `?database=` query parameter once bypassed a path-only check.

The rejected alternative is always kept where it can be measured. The penalty
architecture survives as an ablation arm reachable by a constructor flag, and it scores
about 1.8 points below the best-performing arm and half a point below the matched
control (§6.3). The choice is defended with a number rather than an argument.

### 4.2 Provenance is a data structure, not a comment convention

§2.2 describes the contract. What makes it hold under pressure is that provenance is
carried in the artifacts rather than reconstructed later.

The fits battery emits `(value, origin)` pairs and a hand-rolled YAML writer renders
`key: value  # origin` per line, because pyyaml cannot write per-line comments and the
comments are the point. Grade-C assumptions propagate transitively: a 2024 circuit whose
mass attribution came through the 2026 pool is tagged "grade C via AR-10 fuel — through
the pooled k_m" even though its own era's fuel figure is verified. Ninety-one lines in
the generated artifact carry that flag.

Evaluation rows carry an envelope — model versions, config hash, seed fingerprint, git
commit, and a scope block. Scope exists because without it a two-circuit smoke row and a
480-race row are indistinguishable on disk, and the report would print the smoke number
under the full run's claim.

### 4.3 Store the flagged superset, filter at the point of use

The cleaning contract keeps every ingested row and stores derived flags rather than
writing a cleaned subset. In-laps and out-laps poison a pace fit but are exactly what a
pit-timing fit needs; non-green laps poison both but are what an event-rate fit is made
of. Cleaning at write time makes every cleaning decision irreversible, so ingest flags
and fits filter at query time.

The same principle governs how misses are reported. The synthetic layer's held-out
validation failed — 0 of 4 circuits within the KS target — and the failure ships with
its mechanism attached rather than being tuned away. Tuning a constant on the held-out
rounds to close that gap is precisely the contamination the frozen split exists to
prevent, so the honest move is to publish the miss and name the cause.

### 4.4 Determinism, and the difference between deterministic and pure

Byte-determinism is bought deliberately: a total `ORDER BY` on every fitting query
(float summation order changes the last digit), sorted keys at every level of every
generated artifact, and generated-at watermarks that describe the data rather than
reading a clock.

The evaluation report went one step further and had to learn the difference between
deterministic and pure. Rendering the same store twice in one process gives identical
bytes; that test passed while the report still embedded the filesystem path its figures
happened to land in. The fix was to make figure links always name the committed layout,
and the test that catches it renders in three separate subprocesses under different
`PYTHONHASHSEED` values, because Python's hash salt is fixed for a process's lifetime
and the in-process check cannot see set-iteration drift.

### 4.5 Layering and the hot loop

The environment's `step()` is called tens of millions of times per training run, so the
constraints on it are structural: every constant is distilled at construction into a
frozen scenario object, state is a struct of numpy arrays rather than car objects, and
nothing pandas-shaped is reachable from it. That last rule is enforced by a test that
spawns a clean subprocess, imports `senna.env`, and asserts no module containing
"pandas" is in `sys.modules` — the pandas-using strategy extractor is deliberately not
re-exported from its own package to keep the import graph clean.

Elsewhere the layering is: fitters are pure functions (frame in, frozen dataclass out,
thresholds as arguments, no config reads, no I/O); exactly one module per subsystem
touches the database; notebooks contain narrative and call into the package, never the
reverse. The five fitting notebooks hold 59 to 107 lines of code each, every computation
an import.

### 4.6 Defence in depth against contamination

The 2026 calibration/validation split was frozen on 14 July 2026 — the day the data
feature's plan was approved, before any fit existed — and recorded in
`configs/data_split.yaml` with a header stating that editing it afterwards is
train-test contamination.

It is enforced at three independent layers, because one forgotten `.where` clause
silently leaks the test set:

1. **SQL** — every calibration query appends the round filter.
2. **Runtime** — the guard function raises, naming every offending round.
3. **Import boundary** — an AST walk over each module asserts that only the two
   sanctioned modules import the held-out data loader. It is parsed rather than grepped
   so a comment mentioning the module stays legal, and it asserts the module list is
   non-empty so a package rename cannot make the check vacuous.

### 4.7 Design the guard so it can actually fire

The subtlest recurring lesson. A check that compares a variable to itself always passes.

When the explainability pipeline writes a surrogate and then builds cards from it, the
version guard reads the version back off disk from the manifest it just wrote, rather
than passing the version along in a variable. Passing it along would compare a variable
to itself — a check that can never fail.

The database-guard tests *discover* every test module containing a destructive call
rather than listing them, because a hard-coded list cannot notice the new module that
forgets the guard; a second test asserts the discovery is non-empty so it cannot go
vacuous. The evaluation suite's own review found four tests that passed against
deliberately broken code — a path tautology, two renders in one process, a hard-coded
module list, and a config key nothing read — and each fix carries a canary that the
exercise actually happened.

---

## 5. Subsystems

Each subsystem below follows the same shape: what it is for, the decisions that shaped
it and what they rejected, how it is built, and how it is verified.

### 5.1 Data ingestion and the store

**Role.** A one-time bridge from two public sources into local Postgres, so no later
stage ever queries the internet. Every Race and Sprint session from 2022–2026 is fetched
once, flagged rather than filtered, written transactionally with a per-session
checkpoint, and audited by a committed per-season quality report.

**Sources, and one that is unreachable by design.** FastF1 is pinned at `>=3.7,<4`
because 3.7 is the Jolpica-backed line released after the Ergast API shut down in early
2025 (`R-04`, `F-10`). The rejection is enforced rather than asserted: a test greps
every tracked source file for the dead service's name, assembling the search string at
runtime so the guard survives its own scan — the first version failed CI on its own
filename. OpenF1 supplies historical pit and stint data from 2023 onward; its real-time
tier is paid and 2022 does not exist there, so the client raises before any network call
for an out-of-range year (`R-05`).

**Resumability as a transaction property.** The checkpoint flips to `loaded` as the last
statement inside the same transaction that writes the rows. A separate mark-loaded step
admits a checkpoint that lies in either direction; an `in_progress` state would then
need repairing after a crash. An absent row means never attempted, so there is nothing
to reconcile after a kill. This mattered immediately — FastF1's own 500-calls-per-hour
budget killed the first bulk run, and nothing was lost.

**Two idempotency patterns, split on whether a natural key exists.** Data tables
delete-and-reload, because race control messages have no natural key: real feeds repeat
identical messages and no constraint can identify "the same row". Identity rows (events,
sessions, checkpoints) upsert, because the FastF1 pass and the OpenF1 pass share them
and each must refresh only the columns it actually knows.

**A 404 is data, not an error — at exactly two endpoints.** The pit and stint endpoints
treat 404 as zero rows; raw fetches still raise so a mistyped path fails loudly. This
overturned an earlier decision: the first bulk run excluded nine early-2023 sessions
citing "no upstream data", then no-stop sprints returned 404 from one endpoint while the
sibling endpoint returned real rows for the same session. The exclusions were reverted,
because an exclusion over one empty endpoint would have discarded real data and put a
false gap in the quality report.

**Implementation.** 1,611 lines across ten modules. The orchestrator (`ingest.py`, 558
lines) owns the resume loop and the single-transaction write; `schema.py` declares twelve
SQLAlchemy 2.0 mapped classes; `cleaning.py` is the specification's cleaning contract as
pure functions with injected thresholds; `fastf1_loader.py` is the package's only FastF1
import site, with the on-disk cache enabled before any other call; `db.py` holds the
disposability guard; `snapshot.py` produces the frozen data archive. Alembic migrations
rather than `create_all`, because the second migration had to alter a live schema —
adding a dry-race flag to `sessions`, relaxing a pit-stop column to nullable — against a
database already holding three seasons of laps.

**Verification.** Fifty-plus tests including seven that run against real Postgres
transactions (kill-mid-ingest then rerun equals a clean single run; a crash inside the
write transaction leaves no partial state), twelve on the wipe guard, and virtual-time
tests on the token-bucket throttle. CI runs `alembic upgrade head` then `alembic check`
so schema drift fails on push.

**Outcome.** The five committed quality reports (generated 15 July 2026) audit 121,406
laps across 227 checkpointed session loads, with zero missing telemetry channels and zero
exclusions. The frozen snapshot taken on 29 July records 123,708 laps across 231
loads — two further 2026 race weekends ingested in both sources between those dates, and
therefore not covered by a regenerated report. Quoting either figure is fine; quoting one
as the other is not, and the reports would need regenerating to close the gap. Cleaning
cost for 2024 as the representative season: 3,259 of 29,023 laps dropped as inaccurate
(11.2%), 1,721 in/out laps separated, 2,143 flagged non-green.

### 5.2 Physics fits

**Role.** Turn the cleaned store plus the telemetry cache into every physics constant the
simulator claims: tyre degradation, joint fuel/evolution pace, event hazards, pit loss,
energy integrals — 1,765 leaf values, each carrying the notebook that produced it.

**The identifiability problem, and reporting it honestly.** Fuel burn and track
evolution both make laps faster as a race progresses. Fitting either alone books the
other's share of the shared downward trend, so they are estimated in one regression
(`E-10`) with session, driver and compound fixed effects.

But constructed fuel inside a single race is exactly affine in lap number, so the two
effects have no unique solution there. The fit is therefore per circuit per era, pooled
over that circuit's dry races — a recorded divergence from the specification's literal
"joint fit per race". When the variance inflation factor exceeds its threshold the code
refits *without* the fuel column, reports the combined trend the data always pins down,
and marks the circuit `identified: false` rather than reporting the arbitrary split the
regression produced anyway.

The pooling rule came from a diagnostic worth stating: pooling every weak estimate across
the 23 fitted 2024 circuits gave a mass sensitivity of −0.0055 s/kg, meaning a heavier car
laps faster. That is a bias signature, not noise. Identification comes from post-interruption laps, which also carry
cold tyres, a bunched field and fresh rubber, and the fit books those pace effects to
fuel. So the pool takes identified circuits only, inverse-variance weighted. Of 29
circuit-era joint fits, exactly one is identified — Canada 2026, whose sprint weekend
gives the pooled fit two sessions of differing race length and enough departure from a
straight fuel line to separate the two effects, at a variance inflation factor of 23.6
against a threshold of 30.

Reporting one identified fit out of 29 is a stronger result than reporting 29 confident
ones, and the notebook prints both pools side by side so the diagnostic survives.

**Degradation without double-counting.** The tyre wear curve is fitted on the joint fit's
*partial residuals* — the raw residual with the age terms added back — so the power law
cannot re-explain fuel or evolution. The fitter raises rather than filters when handed
in/out or inaccurate laps: silently dropping them would hide an upstream contract break,
and an in-lap's +20 s sits at stint end where it reads as a tyre cliff, corrupting
exactly the coefficient the fitter exists to produce.

**Small-sample statistics, chosen for where the data is thinnest.** Hazard bands use the
Wilson score interval rather than the normal approximation, which collapses to zero width
at zero-of-n — exactly where most circuits sit with four or five races. The per-lap hazard
conversion carries a boundary shrink, because the first version produced `log(0)` for a
circuit with one race and one safety car, which simulated as a safety car every lap of
every race.

**Implementation.** 1,591 lines across twelve modules, plus five notebooks holding 59–107
code lines each. The orchestrator runs six stages in declaration order because declaration
order is dependency order. No statsmodels: variance inflation factors, coefficient standard
errors and condition numbers are computed by hand over the same numpy design matrix, which
keeps one dependency and one code path.

**Verification.** A synthetic race with injected coefficients (57 laps, 20 drivers, a
safety-car window, staggered stops) proves the estimator recovers what was injected when
identification exists, and flags the clean race where it does not. Safety-car laps carry
+35 s and in/out laps +20 s deliberately, so a fitter that fails to exclude them cannot
pass the recovery tolerance — the filter is tested by consequence, not by inspection.

### 5.3 Circuit ribbons

**Role.** One self-contained GLB track mesh plus a metadata sidecar per circuit, built
from the fastest clean lap's GPS telemetry, with every look-only number flagged stylised.

**Frames that do not flip.** The ribbon is extruded along rotation-minimising frames
computed by double-reflection parallel transport, not Frenet frames. A Frenet normal
flips 180° at every inflection and hairpin, and a ribbon edge extruded along a flipping
normal turns inside-out (`E-17`). The test computes the naive Frenet baseline *inside the
test* and asserts it flips before asserting the shipped method does not — the rejected
alternative proves itself rejected.

The closed-loop twist residual is measured and spread linearly back over all stations, so
the frame is periodic and the start-finish quad carries no seam. Half-width is
`min(6 m, 0.9 × local corner radius)`, because Monaco and Hungary have corners tighter
than a fixed ribbon is wide and the inner edge would cross the centreline.

**Self-intersection is a shipping gate, not just a test.** The builder re-runs the
intersection check on the built vertices and refuses to export a crossing ribbon, keeping
the previously built one instead — a degraded session must not evict a good ribbon.

**Elevation and banking are decoration and say so.** Smoothed Z exaggerated 1.5×, or flat
plus camber where the Z channel is degenerate; both branches stamp `stylised` into the
metadata the UI surfaces, and the dashboard's legend renders that caveat from the flag
rather than from hardcoded copy (`F-12`).

**Outcome.** Twenty circuits, 2.3 MB of GLB, ~119 KB average. The library is generated
from ingested data rather than a hand-listed calendar, so a circuit the season has not
yet visited is simply absent — pinned by a test asserting the count is never 22 or 24.

### 5.4 The synthetic 2026 generator

**Role.** Age the fitted 2024-era physics forward into 2026 dynamics for every circuit,
including circuits the 2026 season has not yet visited, through eight named
transformations — then grade the result out of sample against real 2026 rounds.

**Physics scaling, never a learned generator** (`R-09`). The specification states the rule
directly: every transformation is a formula that can be defended line by line. A GAN would
have no per-term interpretability and no way to attribute the sim-to-real error to a
mechanism. That attribution is exactly what the validation delivered (below).

**A grey-box effective car instead of sourced aero constants.** Rather than feeding
grade-B published aero figures into every lap, a least-squares fit against 2024 telemetry
recovers an effective power and an effective drag coefficient from `m·a = P/v − βv²`.
Density, frontal area, engine torque and rolling resistance are absorbed into two measured
numbers; only the 2026 deltas applied on top are sourced. The straight-line profile is
integrated by RK4 over distance with the power taper implemented as specified — full to
290 km/h, linear to zero at 355 — and a closed-form check pins the integrator exactly
where drag is zero.

**A derived quantity beats a noisy regression.** The lift-and-coast cost coefficient is
computed by sweeping lift depth on the already-calibrated point-mass model and taking the
through-origin slope of extra time against harvested energy. Regressing it off real race
laps would be confounded by traffic, tyre state and fuel.

**The transformations.** T1 powertrain reprofile (straight-line speed, full-throttle time,
deployable energy); T2 aero scaling with a *fitted* corner-speed exponent (0.2239 globally,
against the specification's 0.25 fourth-root prior, which survives only as a fallback);
T3 mass shift through the fitted mass sensitivity and nowhere else; T4 energy accounting
(harvest supply, clipping, deficit); T5 2026 compounds via degradation refit plus cluster
transfer; T6 fuel budget; T7 overtaking model refit by hand-rolled Newton-Raphson over
21,159 mined opportunities; T8 residual recalibration against real 2026 calibration rounds.

**The result, and it is a failure.** Against held-out 2026 rounds 7+, the lap-time
Kolmogorov–Smirnov distance is 0.704 (Barcelona), 0.872 (Britain), 0.918 (Austria), 0.946
(Belgium) — 0 of 4 within the 0.15 target. The cause is in the same artifact:
simulated laps come out 3.7–6.1 s *faster* than reality, because in the recomposition
step the drag-reduction straight-line gain outweighs the downforce-reduction corner loss.
The pooled residual only partly corrects circuits with no calibration data, so the
distributions barely overlap.

This is reported as metric M8 with its mechanism attached. The fix — rebalancing the
corner-versus-straight physics on *calibration* circuits only — is named as future work
rather than applied, because tuning on the held-out rounds is the contamination the
frozen split exists to prevent. A validation that catches a real modelling error is
doing its job; the honest response is to say so.

### 5.5 The environment

**Role.** `F1RaceEnv`: a 22-car, one-decision-per-lap Gymnasium environment over the
fitted physics. A 32-dimensional observation, a `MultiDiscrete([6, 4])` action under
per-head masks, a three-term reward, and seed discipline strict enough that a subprocess
worker is stateless.

**Masks, with reasons.** Discrete legality lives in the mask (pit lane closed, compound
versus track wetness, the two-compound rule, the attack-mode state-of-charge floor,
and a guard against pitting onto a compound the circuit has no fit for); continuous
legality lives in physics clipping (deployment to what the store and the deployable
budget allow, SOC hard-clipped to [0, 4]). Every masked rule carries a reason code that
is republished in the step info every lap, because the decision cards must be able to say
*why* an option was off the table, not merely that it was.

No head may ever be left entirely False, since the policy cannot sample from a fully
forbidden head. The invariant survives even the forced last-lap pit, because scenario
construction refuses a circuit with fewer than two fitted slick compounds.

**The unfitted-compound guard, and why it landed before the headline runs.** An unfitted
slick fell through two disagreeing fallbacks: the dynamics module priced it with the
hardest fitted compound's wear curve, while the observation encoder's identity fallback
reported grip 1.0 forever. An agent could therefore learn "the soft tyre at Suzuka never
degrades" from a fiction. The fix is a mask, not a penalty, even in the penalty ablation —
because this is a data limit rather than a sporting rule, and there is no correct price
for a tyre that was never fitted. It was recorded as blocking the headline training runs
rather than shipped as a hotfix, since it touches the mask contract.

**Three reward terms, and the twelve that were removed.** Pace shaping scaled per circuit,
a potential-based position term, and terminal championship points. The position term is
potential-based with the environment's discount at 1.0, so any position path returning to
its start sums to exactly zero — which kills the lose-and-regain oscillation pump that the
earlier twelve-term design rewarded (`F-15`).

Those twelve terms are not deleted. `reward_v2.py` reconstructs them from the
specification's own quotes *including the pathologies*: the asymmetric position term that
nets +0.2 on a swap cycle, the bonus that pays for boxing early on barely-worn tyres, the
fastest-lap bonus resurrecting a point abolished in 2025. Reproducing the flaws faithfully
is what makes the ablation comparison honest.

**The deterministic twin, and why same-seed pairing is a fiction.** The environment
consumes randomness at a policy-dependent rate — a tyre only rolls for failure past its
cliff, a stop only draws service time when it happens — so two policies handed the same
seed diverge in their events after the first different decision. Paired comparison
therefore runs on an `EventTrace`: one leg records what the environment *applied* (status,
red flags, weather, wetness, failures, rival stops, grid, driver offsets), and both legs
replay that frozen trace. Recording what was applied rather than how rivals decided it
means a later rewrite of the rival model leaves old twins replaying identically.

On a twin the ego's own tyre failure is recomputed rather than replayed, because the ego
may run a completely different strategy — and it is applied as a hard deterministic cap
rather than a hazard roll, so an oracle stint cannot win by banking on a lucky
non-failure.

**Honest simplifications, declared.** Overtaking emerges from lap-time differences plus a
dirty-air term rather than an explicit pass probability, because a second unfitted
probability would be a second thing to defend. Classification is derived from cumulative
race time and never swapped in place, which is what makes the FIFO pit lane and double-
stacking meaningful.

**Verification.** 94 tests in the environment package, including two Hypothesis property
tests marked slow: ~100,000 random-legal transitions asserting that the executed action
was legal under the mask read before stepping, that SOC stays within bounds, and that
harvest minus deployment is conserved; plus a second property test at a circuit with only
two fitted compounds asserting the unfitted one never appears.

**Throughput.** 18,477 environment steps per second aggregate across 12 subprocess workers
on a 10-core Apple Silicon laptop, measured with the per-step mask fetch on the clock.
That prices the 8-million-step training budget at about seven minutes and is what made the
three-seed plus four-ablation plan safe to commit to.

### 5.6 Opponents, baselines and the oracle

**Role.** Everything the agent is measured against.

**Rivals vary along their strategic character, drawn per race.** Three archetypes —
undercutter, tyre-saver, opportunist — differ in pit-trigger tyre age, safety-car response
probability, lap-noise scale and slick-compound preference. The safety-car response is the
axis `E-06` names, and it is applied as a per-car Bernoulli against a per-race drawn
probability rather than a shared deterministic rule, so the field's answer to a
neutralisation is a distribution rather than a memorisable stampede. Two simplifications
are declared: rivals hold balanced energy mode, and archetypes carry no mean pace offset —
the noise scale widens the spread without moving the mean — because tying strategy style
to car pace would confound the paired-baseline metric.

Train and test bands are disjoint by construction and rejected at parse time if they
overlap. The test band is pushed *further* toward each archetype's character, so the
held-out result measures robustness to harder unseen opponents rather than in-distribution
generalisation — and the scripted baseline is run under both bands so opponent difficulty
is separable from the agent's own gap. Measured: the same heuristic finishes P6.852 under
the train band and P6.631 under the test band, a shift of 0.221 places.

**Three baselines** (`A-07`): an engineer heuristic mirroring a real pit wall's ladder, a
replayed-real strategy that runs the recorded stops of an actual race, and random-legal as
the floor. The replay baseline runs balanced energy everywhere and counts its deviations —
a 2024 strategy carries no 2026 energy decision, and inventing one would fabricate the
exact thing the counterfactual metric measures. When the mask blocks a recorded stop it
defers a few laps then snaps to the nearest legal compound and increments a counter that
is reported with the result.

**The oracle publishes its assumptions.** A two-stage dynamic-programming strategist gives
the regret metric a ceiling, and its seven assumptions are stated verbatim in the module
docstring: full information, rivals do not react, deterministic physics, greedy per-lap
energy, fixed start compound, a stop cap with a ranking stage that ignores traffic, no
mid-race replanning. An easy oracle flatters the agent, so the limits are published rather
than implied. Two subtleties earn their complexity: the ranking stage's pit charge is
status-aware, because a flat charge overstates every plan that boxes under a neutralisation
and drops genuinely best plans below the shortlist cut; and pit-entry legality is read from
the *previous* lap's wetness, because that is the mask the agent actually faced.

### 5.7 Training

**Role.** Train the agent with MaskablePPO through the competence-gated curriculum, and
leave an auditable trail rather than just weights.

**Why MaskablePPO, and why not DQN.** Masks are applied inside the action distribution, so
illegal actions have probability zero in both rollout and update. DQN was cut for an
architectural reason rather than a compute one (`R-06`): the action space is two independent
heads, and the available implementation requires a flat discrete space. Flattening back to
the earlier design's twelve entangled actions would undo the very fix that separating the
heads exists to make — the audit finding is worded exactly that way ("a flat 12-action
space entangles two independent decisions", `F-18`).

**Budgets are ceilings, never schedules** (`R-12`). This is enforced by making the
alternative unrepresentable: no gate function takes a step *budget*. Stage A and Stage B
are pure functions of an evaluation history alone; Stage C's stagnation rule does take the
current step, because "no improvement for a million steps" is defined in steps — but it
still cannot see the ceiling. The budget appears exactly once, as the value passed to the
learning call, and a stage that passes its gate logs `transition` while a stage that runs
out logs `budget_stop`. All three headline runs exited by gate; none by ceiling. The
promoted seed passed Stage A at 294,912 steps of a 1.5-million ceiling, the other two at
196,608.

**Gates that survived their own review.** Stage A's plateau test compares best-of-window
against best-before rather than consecutive evaluations, because the naive reading passed a
policy still gaining nearly 3% over the window. Its time bar is one-sided: a faster-than-
reference agent passes, and an implausibly large beat passes *flagged*, because the solo
reference is near-optimal rather than provably optimal. Stage B pairs on recorded event
traces rather than shared seeds, stores the baseline's own twin roll rather than its noisy
recording run, and refuses anything but exactly the configured pair count — a silently
dropped seed would bias the finish-ahead rate.

**One schedule over the summed ceilings.** Learning rate and entropy decay are driven by
the true global step rather than the framework's per-call progress, which would re-anchor
at each stage boundary and jump the learning rate back up exactly when the observation
distribution shifts.

**A gamma mismatch, quantified rather than hidden.** PPO trains at 0.997 while the
potential-based shaping telescopes exactly only at 1.0, so the invariance holds
approximately with a residual of about (1 − 0.997) × 0.1 × position per lap. The
specification wins; the sensitivity runs are wired and were not run, which is stated
rather than implied.

**Outcome.** Three headline seeds scoring 6.355, 6.295 and 6.542 mean validation points;
seed 331 promoted as `senna-ppo-5e3ddb15d584-C-01769472`. Full three-stage wall clock: six
to twelve minutes per seed, 25 minutes for the slate.

The slate was trained twice during F18, on the same physics but under two different
recorded fingerprints, and every seed returned an identical score at an identical step.
So did all eight ablation arms and the era-matched fine-tune: eleven runs, two
independent slates, agreement to the last digit of a float. That was not a designed
experiment — the second slate exists only because a config edit moved the fingerprint —
but it is the strongest determinism evidence the project has.

### 5.8 Ablations

**Role.** Turn the training pipeline into evidence about its own design choices.

**Arms differ only by config bytes.** Each arm copies the configuration tree into an
overlay directory and writes its environment overrides there, then calls the ordinary
training entry point. No arm-specific branch exists inside the training loop, and two arms
cannot share a fingerprint. All four run Stage C from scratch at 4 million steps so the
first arm is a matched control the others differ from on exactly one axis. Every arm,
including the penalty arm, is *scored* in the default masked environment, so the numbers
are comparable — the penalty arm's violations live in its training curves, never in its
selection score.

**Findings.**

| Arm | Mean points (2 seeds) | Reading |
|---|---|---|
| no_curriculum (control) | 5.740 / 4.078 (mean 4.909) | The matched baseline |
| penalty_constraints | 3.938 / 4.917 (mean 4.428) | Penalties cost 0.48 against the control and 1.8 against the best arm |
| reward_v2 (twelve terms) | 3.815 / 4.052 (mean 3.934) | The old reward costs ~1 point against the control |
| terminal_only | 6.638 / 5.828 (mean 6.233) | Matches the headline within noise |

The penalty arm's two seeds straddle the control (one below, one above), so the
architectural case does not rest on that margin — it rests on what the violation curve
shows and on what masking makes impossible. Under random play the penalty environment
sees about 22.6 violations per race; the masked environment cannot produce one.

The dominance ratio — the specification's guard on shaping overwhelming the terminal
objective — is 2.221 for the headline and 0.029 across the twelve-term arm's two seeds. That is the
reward-hacking mechanism as a single number: the twelve terms bury the objective they were
meant to support.

The terminal-only result is the uncomfortable one and is reported as such. Shaping is not
performance-load-bearing at this budget, so the honest claim is that the three-term reward
is kept for per-lap credit legibility and as a reward-hacking rail, *proven not assumed* by
ablation — never that it drives performance.

### 5.9 Explainability

**Role.** Make every decision explainable, with the explanation's own fidelity printed
beside it.

**The plan that was impossible.** The earlier design specified tree-SHAP on the policy
network's outputs. Tree explainers do not accept multilayer perceptrons, and the
model-agnostic kernel explainer on the evaluation set was priced at roughly a billion
forward passes (`F-25`). That is a different category from slow, which is why the
replacement is a redesign rather than a tuning exercise.

**Two paths** (`A-04`). Path one distils the policy into per-head gradient-boosted
surrogates and runs exact TreeSHAP on those for every decision. Path two runs a gradient
explainer on the true network for a 500-decision sample and reports the rank correlation
between the two — the integrity statistic that turns the approximation into a stated
transparency property. The separation is structural: the tree explainer's only argument is
a booster, and exactly one module touches the network's internals.

**Distil the unmasked distribution.** The surrogate learns the policy's *unmasked* head
distributions, because the mask depends on per-circuit fitted compounds and a last-lap
rule that are not recoverable from the observation — so masked targets would be
multi-valued across circuits and would cap fidelity at the mask disagreement rate. The
mask is recorded alongside and re-applied when the card is built, and fidelity is scored
the way a card consumes the surrogate: masked to legal actions, renormalised, then top-1
agreement and mean divergence.

**Distil-or-refuse.** The specification says to deepen the surrogate before shipping
explanations; the code makes that literal. A three-rung ladder is walked shallow to deep
and the first rung clearing 0.90 top-1 agreement wins; after the last rung the pipeline
raises and nothing partial ships. Both models cleared the first rung.

**Two honesty traps in the counterfactual flip probe.** The probe sweeps a feature until
the policy's call flips, on the *true network* under a *rebuilt* mask. Trap one: the mask
must be recomputed at every sweep point, because sweeping wetness or state-of-charge
crosses mask thresholds and reporting a flip onto an action the mask forbids there would
be a lie. Trap two: the sweep must walk outward from the recorded value, because the first
implementation scanned from index zero and returned the range floor for any decision
sitting high in its range — a true sentence about the sweep and a false statement about the
decision.

Ranking flip candidates across all 32 dimensions rather than the card's top five lifted
flip-line coverage from 6.2% to 48.2%, because on 89.6% of cards the strongest driver is a
one-hot (compound, track status, the override window) that no sweep can cross.

**Background matters as much as the explainer.** The 1,024-state background is stratified
by circuit, race phase and track status with an *even* share per stratum rather than a
proportional draw. Safety-car and virtual-safety-car laps are a few percent of all laps,
and a proportional draw would nearly erase exactly the states the interesting pit calls
live in — every safety-car call would then be explained relative to an almost entirely
green baseline.

**Never explain a ghost** (`E-15`). The surrogate is written before a single card exists,
and the card builder reads the version back off disk from the manifest it just wrote. A
retrain invalidates every card by construction.

**Outcome.** Headline model: 99.76% top-1 agreement on held-out pit decisions, 98.19% on
energy-mode decisions, mean rank correlation 0.548 across 500 cross-checked decisions with
all 500 positive and a minimum of 0.222. 14,460 cards across 240 validation races. The
era-matched model scores 99.15% and 98.24% with 13,760 cards.

Both surrogates were refitted after F18 and the two moved differently. The era-matched
one improved everywhere. The headline one halved both KL divergences while giving up
about nine tenths of a point on the mode head's top-1 and falling from 0.687 to 0.548 on
the gradient cross-check — a surrogate closer to the policy's distribution that crosses
the argmax boundary more often on near-ties, and a cross-check comparing against a
different network's gradients. The claim that survives unchanged is that no sampled
decision had the two views disagreeing about direction.

### 5.10 Serving

**Role.** Give the simulator an address: validate and enqueue in the API, simulate in the
worker, stream from storage.

Design decisions are covered in §3.2 (the process split, the playback clock, the worker
topology). Three more are worth stating.

**The cache key gained a scenario digest, recorded as a divergence.** The specification's
literal key is model version, environment hash and seed — which means Bahrain and Monaco
on seed 42 collide into one cached race. The shipped key adds a digest over the scenario
fields plus a purpose discriminator, so a counterfactual leg can never satisfy a plain
simulation request. The model version and environment hash come from the served triplet's
manifest and are never recomputed at serve time, so a retrain cold-starts its own cache
namespace by construction rather than by a flush someone must remember (`E-15`).

**A cache hit is checked, never trusted.** A queued or running row older than twice the job
timeout is treated as a work horse that died, its key deleted, and the run re-queued.
Without that, the key answers with a corpse for seven days and the WebSocket waits forever.
Concurrent identical requests are resolved by an atomic Redis claim rather than a lock, so
double-clicking costs one insert and zero races.

**The era registry degrades loudly.** Weights without a fitted surrogate are treated as
"not baked yet", because a missing surrogate would fail the pairing check mid-job and turn
a graceful fallback into a broken endpoint. Until the era-matched surrogate existed, the
counterfactual view served the frozen 2026 model and wrote `pending-F14` into the run
config, which the dashboard rendered as a visible caveat.

**Outcome.** Twelve REST endpoints plus one WebSocket across eight route modules; 84 tests
across the API and serving packages, including a health-latency test that measures the
250 ms threshold directly while a stream is being consumed and a worker drains a full
SHAP-per-lap race in-process.

### 5.11 The dashboard

**Role.** Six views — circuit explorer, race replay, energy, tyre surface, live simulation,
counterfactual — and the only part of the system an examiner watches rather than reads.

**Two constraints shape every file.** The frame budget, which in React terms means nothing
that updates at 60 fps may be React; and the interpretability contract crossing the browser
boundary, which means every number on screen arrived from an API response and the dev
overlay traces it back to the response that carried it.

**Nothing re-renders at frame rate.** Per-frame data mutates through refs, the render loop
reads state through a non-subscribing getter, and the transport slider tracks the playhead
through a transient subscription that writes the DOM value directly. React renders at lap
rate, driven by selectors whose output changes once per lap.

**Twenty-two cars in three draw calls.** One instanced mesh for bodies with per-instance
colour, one for the detail fin, and one quad instanced mesh whose per-instance UV offset
picks each car's code out of a single canvas atlas. Draw calls, not triangles, kill a frame
budget. DOM labels are capped at four — podium plus selection — with everyone else on
instanced sprite text, and the cap is a pure function so a property test can pin it.

**One canvas per route, enforced architecturally** (`F-28`). The shell owns no canvas, each
canvas view owns exactly one, and the router swaps route elements in a single commit — two
canvases would require two mounted routes, which the router cannot do. The counterfactual's
split screen is the interesting exception: one canvas behind two pane divs, each pane
scissor-rendering its own scene, sharing one camera so any visual difference between halves
is strategy rather than viewpoint.

**Motion between laps is declared synthesis.** The simulator is lap-quantised, so per-lap
progress fractions are interpolated with a monotone cubic — Catmull-Rom was rejected because
its overshoot renders as a car visibly driving backwards. The caption saying so is exported
from one module and rendered verbatim by all three views that use it.

**Generic liveries, enforced by test** (`F-29`). Eleven invented team colours, two cars each,
codes C01–C22. A test walks every shipped source file against a deny list of team, sponsor
and driver marks; it is the one place in the frontend those names may be spelled out.

**Outcome.** 7,900 lines of TypeScript, 155 tests across 30 files. The full field renders
in 3 draw calls, countable from the three instanced meshes the scene mounts; the whole
replay scene was estimated at about 9 against the 150 budget during planning, and real
draw-call counts are read from the dev overlay at runtime rather than committed, because
the test DOM cannot see them.

### 5.12 Evaluation

**Role.** Roll the frozen agent through the eleven-metric battery on held-out ground — 24
circuits × 20 reserved test seeds against the held-out rival band — and write one
provenance-stamped row per metric into a committed store.

**A target without its failure mode is not evidence.** Every metric carries a gaming note in
its configuration that the report prints verbatim: how this number could be made to look
good without the underlying behaviour improving. M1's note names weak opponents, which is
why the held-out rival band exists and why the scripted baseline is run under both bands.
M2's names simulator optimism: the agent optimised the very simulator it is scored in, while
real teams optimised reality.

**Statistics declared before the roll.** The counterfactual metric's claim is an exact paired
sign test with the bootstrap interval explicitly labelled descriptive, and the payload
carries that label. At ten races the test needs nine wins to clear alpha. Fixing the ten
races, the test and the threshold before the first roll is what makes reporting a 4W/5L/1T
wash legitimate rather than an invitation to renegotiate the analysis.

**Two rolls per race, for two different questions.** The live roll is the deployment world
(stochastic pace, drawn service times, real failure hazard) and the descriptive metrics
report on it, because they ask what the agent actually does. The twin replays those same
events with noise off, and the counterfactual metrics branch from it, because they ask what
else the agent could have done in the same race. Pricing an alternative against a noisy
baseline prices the noise.

**Publish the denominator.** The safety-car metric only scores windows with at least one
*informed* lap, because the action for a lap is chosen against the mask built at the end of
the previous lap — grading an onset-lap stop as a safety-car call credits foresight the
agent did not have. Red flags never open a window at all, since a red-flag tyre change is
free rather than discounted.

**Separating what pooling would hide.** Virtual and full safety cars never pool. Pooled, the
result reads precision 0.942 and recall 0.167 over 674 windows — one mediocre skill.
Separated, it reads as one competent skill (full safety car: precision 0.942, recall 0.308)
and one entirely missing one (virtual: zero calls across 300 windows, 134 of them worth
taking). The separation is what turns a mediocre number into a specific, actionable finding.

**The era confound, measured.** Scoring a 2026-physics agent on 2024 races confounds the car
with the strategy. A 2-million-step warm-started fine-tune on the 2024 constants scores 6.336
mean points against the frozen 2026 model's 3.802 on identical 2024 banks — so roughly two
and a half points of a 2026 agent's apparent 2024 performance is the car (`F-24`). The
counterfactual metric runs on the era-matched model.

**Outcome.** Thirteen store rows, three figures, a generated chapter, and the results in §6.

### 5.13 Demo, reproducibility and the freeze

**Role.** Make the system presentable, provable and frozen.

**The demo is engineered, not recorded.** The first ninety seconds are specified as tightly
as an API: a deep link opens mid-race, a decision card slides in with its fidelity badge,
one click reaches the counterfactual split, one more reaches the energy view. Making that
executable needed a mid-race seek — the deep link's lap and speed parameters ride the
WebSocket as a seek after connect and deliberately never enter the request body, because the
cache key is the request's fields and forking it would orphan every pre-warmed run.

A cold link blocks until the simulation completes, so a warming script pre-runs the demo
simulations; the cache guarantees the warmed run *is* the run the link resolves to. A
Playwright check drives a cold browser to the demo URL and asserts cars on track inside the
15-second budget. It also gave a long-standing open question its harness: a near-empty 3D
canvas observed in Chrome weeks earlier. The suspected cause was benign — at 1× only lap 1
exists for the first ninety seconds, so all 22 cars sit stacked at the start line viewed
from over a kilometre away — and with the mid-race seek in place the check passes and the
scene renders fully. The check is local-only by design, so it stands as a manual gate
before recording rather than a CI guarantee.

**The reproducibility pack** (`A-09`). Make targets for the whole pipeline, a frozen seed
manifest, config hashes in every result row, and a data snapshot. Two pieces are worth
noting.

The snapshot is split in half: the archive is gitignored and is designed to ride the
release, while its manifest — name, SHA-256, exact byte count, per-table row counts — is
committed, so an examiner can verify a downloaded asset offline. Restore routes through
the disposability guard because it drops every table first; dump takes no guard, because
guarding the safe direction teaches operators to override guards.

`make verify` proves the chain from a clean clone: the committed chapter regenerates
byte-for-byte from the committed store, the provenance chain is internally consistent, and no
public page carries a broken link. It runs in CI.

**The chain check has two regimes, and getting this right mattered.** The first design —
recompute the config fingerprint from disk and compare against what each row recorded — would
fail *by design*, because the suite rows copy their hash from the training manifest and the
configuration files were legitimately comment-edited afterwards. A from-disk recompute either
goes red on honest edits or pressures nobody to ever touch a comment again. So suite rows are
checked for internal consistency against the manifests the repository actually serves, plus
the one live recompute that is valid (the frozen seed manifest); the two overlay studies
hashed their own inputs at run time, so for them the live recompute *is* the honest check.

**The byte guard caught its own authors.** During this feature's own review, the committed
chapter had drifted one blank line from what the generator emits, because a template edit was
hand-applied to the generated document rather than regenerated. The guard the feature added
found it.

---

## 6. Results

### 6.1 The metric table

Eleven metrics, twelve verdict rows (the safety-car metric splits into full and virtual).
Two met, six missed across seven rows, three reported without a bar. Full numbers,
intervals and gaming notes are in `docs/results/F14-evaluation.md`, regenerated from the
committed store.

| Metric | Result | Previous (two-season physics) | Target | Verdict |
|---|---|---|---|---|
| M1 paired position delta | **+2.279 places** over 480 pairs, CI [1.913, 2.663] | +2.083, CI [1.710, 2.475] | ≥ +1.0, CI excluding 0 | **met** |
| M2 counterfactual vs actual | 1W/8L/1T, p = 0.039, mean −3.66 over 10 races | 4W/5L/1T, p = 1.000, mean −0.60 | ≥ +1.0, sign test p < 0.05 | miss |
| M3 oracle regret | median 30.48 s, mean 71.78 s over 480 races | median 33.09 s, mean 86.98 s | report only | reported |
| M4 energy utilisation | 0.704 of deployable, ceiling 0.912; derates 0.097 | 0.649, ceiling 0.914; derates 0.080 | ≥ 0.90, derates ≤ 0.05 | miss |
| M5 safety-car quality | precision 0.820, recall 0.401 over 377 windows | precision 0.942, recall 0.308 | both ≥ 0.75 | miss |
| M5 virtual safety car | precision 1.000, recall 0.085 over 304 windows | precision undefined, recall 0.000 | both ≥ 0.75 | miss |
| M6 pit-window accuracy | 0.213 of 517 stops within 3 laps of optimum | 0.228 of 457 stops | ≥ 0.72 | miss |
| M7 strategy diversity | 0.653 nats over 24 circuits | 0.226 nats | report only | reported |
| M8 sim-to-real | 0 of 5 circuits within KS 0.15, worst 0.931 | 0 of 4, worst 0.946 | KS < 0.15 | miss |
| M9 tyre failures | **37.92 per 100 races** (182 of 480) | 37.29 (179 of 480) | < 2.0 | miss |
| M10 regulatory legality | **0 coerced, 0 snapped** over 480 races | 0, 0 | 0 by construction | **met** |
| M11 luck share | **0.786** of finishing variance, CI [0.704, 0.861] | 0.758, CI [0.679, 0.820] | report only | reported |

A suite where every metric passes is a suite whose bars were set after the run. These
were set before.

**What the refit did to this table (F18, 11 August 2026).** Every row above was
re-measured on constants fitted over the full 2022–2025 era rather than two seasons of
it. The headline improved: M1 rose about 0.2 places with a tighter interval, oracle
regret fell at both the median and the mean, and the agent finally pits under a virtual
safety car — M5's VSC recall moved off 0.000 to 0.085 at perfect precision, ten calls
and no false positives, against a previous chapter that had to report the agent never
once doing it across 311 windows.

One row got worse in a way that matters more than the improvements. M2 was a null
result at 4W/5L/1T and p = 1.000; it is now 1W/8L/1T at p = 0.039, mean −3.66 places.
The sign test has become significant in the wrong direction: against replayed real
strategies on the era-matched model, this agent now loses reliably rather than
inconclusively. Better physics turned an absence of evidence into evidence of a gap,
which is the more useful result and the one to lead with when discussing limitations.
It should be read with the 25 snapped stops the replay baseline needed and with M8:
the counterfactual is priced inside a simulator whose sim-to-real error is still far
outside target.

### 6.2 What the misses mean

The misses are not independent, and read together they tell one coherent story.

**M1 with M9 is the headline finding.** The agent beats the engineered baseline by two
positions, and part of how it buys them is running tyres past the cliff: 37 failures per
hundred races, mean stint 29.4 laps, longest 76. That behaviour is coherent inside the
simulator, where a failure is a probabilistic cost the agent has implicitly priced against
the track position a longer stint buys — and it is unacceptable on a real pit wall. The
evaluation suite exists to surface exactly this, and it did.

**M4's bar is unreachable at several circuits by construction.** The deployable-energy
figure exceeds what the store can physically deliver there, so the metric publishes an
attainable ceiling (0.914) beside the raw utilisation (0.649). Against what the battery
could actually deliver the agent uses 0.710. Reporting the raw number alone would read as
the agent declining to deploy.

**M5's virtual safety car result is the most actionable.** Zero pit calls across 300 scored
windows, of which the afterstate search says 134 were worth taking. The suspected mechanism
— a virtual safety car's smaller pit-loss discount never clearing the threshold the policy
learned under full safety cars, plus an observation that may not separate the two states
sharply enough — is labelled a hypothesis in the write-up, not a finding, because it was
not tested.

**M6 compares against a ceiling, not a grade.** The post-hoc optimum is found by rolling
every candidate lap on the frozen trace with full knowledge of what happened; the agent had
none of that. It is an information-set asymmetry, and the note says so.

**M8's cause is upstream** in the synthetic transform (§5.4), and the split forbids fixing
it on the evidence.

**M2 is an honest wash.** Four wins, five losses, one tie against elite human strategists
over ten real races. The claim the dissertation can make is precise: SENNA beats a scripted
baseline in simulation (M1), and is competitive-but-not-significantly-better against real
strategies on ten real races (M2). Not "the agent beats humans".

### 6.3 What the ablations proved

The penalty arm lands 1.8 points below the best arm and half a point below the matched
control, with its two seeds straddling that control — the honest reading is that the
architectural argument carries the claim and the numbers do not contradict it. The
twelve-term reward costs about a point against the matched control and buries the
terminal objective (dominance ratio 0.029 against the headline's 2.221).
Terminal-only reward matches the headline within noise, which narrows the three-term
reward's defensible role to interpretability rather than performance.

### 6.4 The novel result

The luck decomposition: fixing the policy and varying event draws against varying decision
noise attributes **75.8%** of finishing-position variance to the event draw, with a
confidence interval of [0.679, 0.820] across 24 circuits at a mean policy entropy of 0.605
nats. Entangled variance — re-sampled decisions meeting different downstream events — is
charged to the decision side, which makes the published figure a conservative lower bound.

This is the answer to a question strategy analytics usually dodges: how much of a result is
the strategy at all. Most of it is not.

### 6.5 Sensitivity studies

Two overlay studies price assumptions rather than asserting them.

**The harvest cap** (`E-02`). The FIA refined the maximum permitted recharge from 8 to 7 MJ
in April 2026. Editing the committed configuration would desync the fingerprint the served
model records and invalidate the whole chapter, so the refined figure runs as an eval-only
overlay on the same seeds. The frozen agent loses 0.133 places and its derate share rises
from 0.078 to 0.182 — it keeps its results and runs out of energy more than twice as often.
Framed explicitly as the frozen agent's robustness, not what a model re-optimised for 7 MJ
would do.

**The borrowed energy coefficients.** The 2024 scenario borrows the 2026 energy-mode fit,
because no 2024 fit of those coefficients exists. Perturbing the four borrowed values by
±50% moves the counterfactual metric by at most 0.46 places against its own 4.7-place
descriptive spread. The borrow is a documented coarseness rather than a load-bearing
unknown — which is a claim now backed by a measurement.

---

## 7. Verification and validation

### 7.1 Testing philosophy

Roughly 486 Python test functions and 155 frontend tests, written before the code they
cover. Four kinds do most of the work:

**Property tests** where the claim is universal. The compliance property drives ~100,000
random-legal transitions asserting legality, energy conservation and state-of-charge bounds.
TreeSHAP additivity is checked over generated feature vectors. The label budget is checked
across every grid size and selection state.

**Tests by consequence rather than inspection.** The fitting fixtures inject +35 s onto
safety-car laps and +20 s onto in/out laps deliberately, so a fitter that fails to exclude
them cannot pass the coefficient-recovery tolerance. The test does not inspect the filter;
it makes the filter's absence fatal.

**Tests that compute the rejected alternative.** The ribbon frame test computes the naive
Frenet normal inside the test and asserts it flips before asserting the shipped method does
not — so the reason for the design is in the test, not just in a comment.

**Meta-tests and canaries.** The destructive-database test discovers modules rather than
listing them, and a second test asserts the discovery is non-empty. Store and report tests
assert that they actually wrote something before asserting properties of what they wrote.

### 7.2 The vacuous-test lesson

The evaluation feature's review found four tests that passed against deliberately broken
code: a path assertion true for every input, a determinism check that could not see
set-iteration drift, a hard-coded module list that could not notice a new module, and a
config key nothing read. A fifth pinned the database guard by pointing the connection at the
real store and calling the real drop — red at the right moment, after erasing the store,
with no operator opt-in.

The response was a rule rather than five fixes: every test must be able to fail for the
reason it exists, and where that is not obvious it carries a canary asserting the exercise
happened. The lesson is written up in full, because a dissertation that shows its testing
maturing is stronger than one that claims it arrived complete.

### 7.3 Continuous integration

Every push runs, over the whole repository: lint, migration application plus schema-drift
check, the fast test suite against ephemeral Postgres and Redis containers, the frontend
type check, lint, tests and production build, a grep of the production bundle for
Docker-internal hostnames, and `make verify`.

One local-only gate exists deliberately: the demo browser check needs a warmed stack and a
real browser, so it runs by hand before recording rather than in CI.

---

## 8. Reproducibility and the freeze

### 8.1 Three tiers

What a reader can reproduce depends on what they have.

**A clean clone, nothing else.** `make verify` — the results chapter regenerates
byte-for-byte from the committed store, the provenance chain checks out, and links resolve.
`make report` rewrites it. No model, no database, no GPU.

**Docker.** `docker compose up --build` gives the full stack, because the frozen models,
surrogates and track ribbons are committed and baked into the image rather than mounted.
`make demo-warm` then the demo URL.

**The full pipeline.** Ingest, fit, synth, train, eval, report — hours of local wall clock.
Seeds come from the frozen manifest; every result row carries the config hash and model
version that produced it. The Postgres snapshot exists with its digest committed; the
release that will carry it is the pending freeze step.

The first two tiers were exercised end to end on 6 August 2026 from a fresh clone of the
remote with fresh volumes: dependencies installed from the lockfile, `make verify` green,
the chapter regenerated with no diff, the stack built and started, the snapshot restored
(123,708 laps and 29,018 decision cards), the demo warmed, and the first-beat browser
check passing in 741 ms. One documentation gap surfaced and is not yet closed: the
README's reproduce section names no way to build the Python environment, and the working
incantation needs a non-obvious index flag because the lockfile pins across two package
indexes.

### 8.2 What the tag will pin

The freeze's last step is unexecuted at the time of writing: `git tag -l` is empty and no
release exists. `docs/freeze.md` is the runbook, and what it specifies is a `v1.0.0`
annotated tag whose message pins the headline model version, the era-matched model version,
the environment config hash, the seed-manifest fingerprint and the snapshot digest
together, so "which exact system produced Chapter 7" has one answer — plus a release
carrying the snapshot archive.

Everything the tag will name already exists and is checkable today; the tag makes the set
citable as one thing. One decision is still open and belongs to the author: if the
submission is a self-contained bundle rather than repository access, the snapshot has to
travel with the bundle or via university storage rather than a release link.

Two artifacts stay outside the freeze deliberately: the 12 GB telemetry HTTP cache, which
rebuilds from the public APIs, and the experiment-tracking history, which is offline-only —
the committed run ledger is the record.

---

## 9. Limitations

Stated plainly, because every one of them is a question an examiner can ask.

**The synthetic layer's transform is wrong in a known direction.** Simulated 2026 laps run
3.7–6.1 s fast because the straight-line gain outweighs the corner loss. Every downstream result
inherits that: the agent is trained and evaluated in a world whose absolute pace is
optimistic. Relative comparisons — agent versus baseline in the same simulator — are
unaffected, which is why the position-delta metric is the headline claim and the
sim-to-real metric is reported honestly beside it.

**One identified joint-pace fit out of 29.** Fuel and evolution are near-unidentifiable
within a race by construction, so mass attribution rests on a pooled coefficient from a
single circuit. The pooled value is used everywhere and flagged everywhere it lands.

**The counterfactual comparison is in-simulator.** The agent optimised the simulator it is
scored in; real teams optimised reality. Ten races is a small sample and the analysis says
so before reporting the result.

**Tyre failure rate is unacceptable** for anything but a simulator, and is the clearest
target for future work: the failure hazard is priced into the reward only through its
consequences, and an explicit risk term is the obvious next experiment.

**The agent is blind to virtual safety cars.** The mechanism is hypothesised, not
established.

**Weather has two modes, not three.** Both the "mixed" and "wet risk" profiles run the same
Markov engine; the requested profile is recorded on the run and echoed by the API so the
distinction survives in the data even though the physics does not honour it.

**The production deploy is an unverified runbook.** Compose is the supported and verified
target; the cloud deployment path exists and is documented as never executed.

---

## 10. Process

### 10.1 One feature, one session, one branch

The build ran as sixteen features, each a single session with a fixed ritual: plan in
read-only mode and stop for approval; branch, write tests first and show them failing,
implement in vertical slices, run subagent reviews, write a lesson; merge with a
non-fast-forward commit and update the index. Tests before code was a hard rule, and every
feature's test-first commit precedes its implementation commits in the history.

Two supporting artifacts fell out of this and turned out to matter more than expected. The
seventeen lessons in `docs/learn/` explain each subsystem in plain language with line-level
walkthroughs — they were written for the author's own understanding and became the source
material for this document. The plans in `docs/plans/` record what each feature intended
*before* it was built, including the divergences it expected, which is what makes the
recorded divergence list (Appendix D) trustworthy rather than retrospective.

### 10.2 AI assistance

This project was built with AI assistance, declared per the COMP702 policy. The
collaboration was structured rather than ad hoc: the specification was the contract, plans
were approved before implementation, tests were written before code, and every diff was
reviewed by two independent automated reviewers against the specification and against a
code-quality standard before it could land. Several findings in this document — the flip
probe scanning from the wrong end, the report's impure figure links, the missing chain
check on the newest artifact — were caught by that review battery rather than by the author
or by the tests.

The dissertation prose is the author's own. This document is a record of the system, not a
substitute for the argument the dissertation has to make about it.

---

## Appendix A — identifier glossary

Identifiers relevant to this document and to the code it describes, with what they govern.
Not all appear in the body; they are listed together because a reader grepping the
repository will meet them. The full registers are in the master specification (Parts 1, 2,
3, 4 and 8).

**Audit findings (`F-xx`)** — defects found in the earlier design.
`F-02` no per-lap deployment cap · `F-06` fuel mass · `F-07` fastest-lap point abolished ·
`F-08` 22-car grid · `F-10` Ergast shutdown · `F-11` OpenF1 real-time is paid ·
`F-12` elevation and banking are stylised · `F-13` telemetry carries no energy channel,
so an ERS proxy from throttle-off oversells what the data contains ·
`F-14` fits require a quality report · `F-15` reward oscillation pump ·
`F-16` compliance by masking · `F-18` independent action heads ·
`F-20` two-compound rule · `F-23` VecNormalize must travel with weights ·
`F-24` era confound · `F-25` SHAP infeasible on the policy · `F-26` no training or
simulation in serving · `F-27` browser-reachable URLs · `F-28` one canvas per route ·
`F-29` trademark exposure.

**Edge cases (`E-xx`)** — behaviours that must be handled.
`E-01` SOC bounds · `E-02` per-circuit harvest cap · `E-03` virtual and full safety cars
never pool · `E-04` red-flag free tyre change · `E-05` pit-lane FIFO ·
`E-06` held-out rival band · `E-08` weather crossover · `E-09` in/out laps ·
`E-10` joint fuel/evolution fit · `E-11` session naming ·
`E-12` resumable throttled ingest · `E-13` a new circuit with no data until its first
session · `E-14` frozen split ·
`E-15` cache and explanation invalidation · `E-16` WebSocket replay from store ·
`E-17` ribbon self-intersection · `E-18` WebGL context loss.

**Removals (`R-xx`)** — what the v3 design deleted and why.
`R-02` twelve reward terms · `R-03` the 4 MJ/lap mechanic · `R-04` Ergast ·
`R-05` OpenF1 real-time · `R-06` DQN · `R-07` unofficial-project footer ·
`R-08` mobile 3D and broadcast cameras · `R-09` GAN for synthetic data ·
`R-12` the 20-million-step budget.

**Additions (`A-xx`)** — what v3 added.
`A-01` action masking · `A-03` decision cards · `A-04` surrogate distillation with reported
fidelity · `A-05` oracle regret · `A-06` paired-seed evaluation with bootstrap intervals ·
`A-07` three scripted baselines · `A-08` luck decomposition ·
`A-09` reproducibility pack · `A-10` era configuration.

**Assumptions (`AR-xx`)** — graded, with sources. `AR-01` MGU-K 350 kW (A) ·
`AR-04` 4 MJ store window (A, verified against the regulation text) · `AR-05` harvest cap ·
`AR-10` ~70 kg race fuel (verified against the 3,000 MJ/h energy-flow limit) ·
`AR-15` OpenF1 rate limit.

## Appendix B — repository map

```
senna/            16,238 lines of Python (with api/ and worker/)
  data/            1,611   ingest, cleaning, schema, snapshot, the wipe guard
  physics/fits/    1,591   the fitting battery
  physics/synth/   1,929   T1–T8 and the 5.4.1 validation
  circuits/          667   telemetry → GLB ribbons
  env/             1,885   F1RaceEnv, masks, dynamics, events, twin, rivals
  strategy/          891   baselines, oracle, plans, rollout
  train/           1,725   curriculum, gates, checkpoints, ablations, selection
  explain/         1,192   distillation, TreeSHAP, flip probes, cards
  eval/            2,796   M1–M11, sensitivities, store, report
  serve/             345   model loader, cache keys, frame builder
  bench/             139   throughput benchmark
api/               1,066   FastAPI routes, schemas, WebSocket
worker/              352   RQ jobs
frontend/src/      7,912   React 18 + R3F 8, six views
tests/            12,367   486 test functions
configs/           4,400   21 yaml files, every constant with provenance
docs/             17,007   spec split, plans, 17 lessons, results, this document
```

## Appendix C — where the evidence lives

| Claim | Artifact |
|---|---|
| Ingested data quality | `docs/data_quality/<season>/data_quality_report.md` |
| Fitted constants and their origins | `configs/physics_params.yaml` |
| Synthetic transformations | `configs/transforms.yaml` |
| Sim-to-real validation | `docs/synth/validation_summary.yaml` |
| Throughput measurement | `INDEX.md` decisions log (OQ-2) |
| Ablation results | `docs/results/F08-ablations.md`, `models/runs.json` |
| Surrogate fidelity | `docs/results/F09-explainability.md`, `models/explain/<version>/fidelity.json` |
| Evaluation results | `docs/results/F14-evaluation.md`, `docs/results/F14/store/*.json` |
| Frozen data snapshot | `data/snapshot/MANIFEST.md` |
| Decisions and their dates | `INDEX.md` decisions log |
| Per-feature reasoning | `docs/plans/F00-plan.md` … `docs/plans/F15-plan.md` |
| Per-feature explanation | `docs/learn/F00-*.md` … `docs/learn/F15-*.md` |

## Appendix D — divergences from the master specification

The plans record roughly thirty divergences and interpretation flags across the sixteen
features. Listed below are the thirteen that shaped the architecture; the rest are mostly
additive response fields and protocol details, and each lives in its feature's plan under
a "flagged divergences" heading. Every row here was recorded in the relevant plan before
the feature shipped.

| # | Divergence | Reason |
|---|---|---|
| 1 | Joint pace fitted per circuit-era, not per race | Constructed fuel is affine in lap number within one race; no unique solution |
| 2 | Corner-speed exponent fitted globally, not per circuit | Five both-era circuits cannot identify per-circuit exponents |
| 3 | Cache key gains a scenario digest | The literal key collides circuits on the same seed |
| 4 | Rival band passed explicitly | The specification's default and the environment's default disagree |
| 5 | Frames in a dedicated JSONB table | The specification's laps columns do not fit per-lap render frames |
| 6 | Era-2024 runs field 20 cars | Grid position must be bounded by the era's own field size |
| 7 | Cards ride the lap message; no separate decision event is emitted | Two specification sections conflict — the explainability section streams cards in an `agent:decision` event that the WebSocket contract does not define; the contract wins |
| 8 | Local WebSocket has no proxy path | The master specification's environment table beat the feature specification's idea |
| 9 | One Dockerfile, two start commands | The two services must never disagree about code or baked models |
| 10 | M1 runs 480 pairs, not 500 | The frozen bank is 24 × 20; minting seeds later is contamination |
| 11 | Additive energy and tyre response fields | The views need served ceilings rather than client constants |
| 12 | Resume-from-pause is sent as a seek, not a speed message | Only the server's seek branch clears the paused flag |
| 13 | Railway deploy deferred | Compose is the verified target; the deliverable is a reproducible codebase |

Plus a fourth provenance origin (`operational`) added to the interpretability contract for
serving-layer engineering defaults.

Two departures are worth separating from that list because they are *not* divergences
from the specification, and calling them so would overstate the discipline. The circuit
builder checks lap length against the lap's own telemetry odometer because no per-circuit
official length exists in the data — recorded in the code, not in the plan. And the
frontend imports routes eagerly where its own plan specified lazy imports, because the
lazy path cannot be exercised under the test DOM — a departure from a plan, recorded
after the fact in the router module.
