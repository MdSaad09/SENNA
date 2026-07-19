# Curriculum ledger

The teacher agent reads this before writing any lesson and appends to it afterwards.
A concept listed here is considered taught: later lessons reference it with one line,
they do not re-explain it.

| Concept | First taught in | One-line definition |
|---|---|---|
| Lockfile (intent vs resolution) | F00 | Human-edited intent file (`requirements.in`, `package.json`) compiled into an exact, machine-generated pin of the whole dependency tree. |
| Pin what breaks, float what does not | F00 | 5.9.1 pin policy: exact-pin only known-breaking pairings (SB3/sb3-contrib, React 18/R3F 8); range-float the rest. |
| Environment markers | F00 | Per-platform conditions on lockfile lines (`; sys_platform == 'linux'`) so one universal lock serves mac and linux. |
| Resolver backtracking | F00 | A dependency solver walking back through old releases to satisfy constraints; fixed by adding a floor on the misbehaving package, not its neighbours. |
| docker compose services and healthchecks | F00 | Named containers on a private network; `depends_on: service_healthy` gates startup on a real readiness probe, not container start. |
| The browser boundary (F-27) | F00 | Docker hostnames are valid server-side only; anything reaching the browser (`VITE_*`) must be a browser-reachable URL or path. |
| Anonymous volume mask | F00 | A bare container path in `volumes:` (`/app/node_modules`) that shadows part of a bind mount so host-native binaries stay out of the container. |
| Tests as forcing functions | F00 | Writing the failing test first so its failure list is the work order (the anchor test drove the 15-file spec split). |
| CI on push (GitHub Actions) | F00 | A clean machine re-runs lint, pytest and vitest from the lockfiles on every push; disagreements with your laptop mean hidden local state. |
| pytest pythonpath parity | F00 | `pythonpath = ["."]` in pyproject makes bare `pytest` (CI) import like `python -m pytest` (local). |
| Spec anchors | F00 | The `Spec anchors:` line in each feature spec, machine-resolved to files on disk by `scripts/check_spec_anchors.py`. |
| Provenance comments | F00 | The interpretability contract applied to constants: every pin/number carries a comment naming its source (spec row, fit, or explicit choice). |
| pandas DataFrames and NaT/NaN | F01 | In-memory tables with typed columns; NaN/NaT mark missing numbers/times, are contagious, and need `pd.isna()`, not `==`. |
| SQLAlchemy ORM vs Core | F01 | ORM classes declare tables once (`Mapped`/`mapped_column`); Core statements (`insert`/`select`/`delete`) do bulk work without per-row objects. |
| async/await and asyncpg | F01 | Coroutines yield at `await` to an event loop; asyncpg only works this way, so DB code is async end to end with one `asyncio.run()` at the top. |
| Alembic migrations | F01 | Ordered, reversible schema-change scripts (`alembic upgrade head`); unlike `create_all`, they can alter populated tables and CI's `alembic check` catches drift. |
| Transactions, unique constraints, upserts | F01 | `engine.begin()` commits all-or-nothing; unique constraints refuse duplicates; `ON CONFLICT` turns insert-or-update into one atomic statement. |
| Token-bucket rate limiting | F01 | A bucket of `burst` tokens refilling at `rate`/s; each request spends one, so bursts pass but the long-run rate is capped (AR-15/E-12). |
| Fixtures and injectable clocks | F01 | pytest injects named builders by argument; passing `clock`/`sleep` as functions lets tests run on virtual time — no test ever really sleeps. |
| Delete-and-reload vs upsert idempotency | F01 | Keyless tables can't upsert; deleting a session's rows and reinserting inside one transaction makes any rerun a clean no-op. |
| Checkpointed resumable batch jobs | F01 | One state row per work unit, flipped to `loaded` in the same commit as the data; reruns skip terminal states, so a killed run loses nothing (E-12). |
| Flagged superset storage | F01 | Store every raw row plus derived flags (`is_green`, `lap_time_imputed`); fits filter at query time, so no cleaning decision is irreversible (E-09/5.3.4). |
| 404 as zero rows | F01 | Some APIs 404 an empty query; where "no rows" is a legal answer the client translates that status to `[]` per endpoint — absence is data, errors stay errors (F-14). |
| OLS with fixed effects | F02 | Least squares on a design matrix with drop-one 0/1 dummy columns per category level, so slopes are estimated within driver/session/compound. |
| Collinearity, VIF and condition number | F02 | Near-linear dependence between regressors; VIF = 1/(1−R²) of one column on the rest, condition number the same worry matrix-wide — both reported per fit (E-10). |
| Identifiability vs noise | F02 | Noise shrinks with data; unidentifiable means the data cannot distinguish two explanations — report what is pinned down and flag the rest (`identified: false`). |
| Partial residuals | F02 | Raw residuals plus one term's fitted contribution added back: "the data with everything except this term removed" — the degradation fit's input. |
| Inverse-variance pooling | F02 | Combine estimates weighted by 1/SE²; minimum variance for unbiased inputs, which is why confounded (not merely noisy) fits must be excluded first. |
| Wilson score interval | F02 | A proportion confidence band that stays usable at 0-of-n and small n, unlike the normal approximation's zero-width collapse at the boundaries. |
| Per-race probability to per-lap hazard | F02 | λ = −ln(1−p)/laps inverts "chance of ≥1 event in L laps of constant hazard"; saturated counts shrink to n/(n+1) before the log (5.5.3). |
| scipy curve_fit with bounds | F02 | Nonlinear least squares for models like a·age^b; bounds keep coefficients physical and p0 seeds the local optimiser. |
| KMeans and silhouette | F02 | Distance-based clustering on standardised features; silhouette scores pick k, and a fixed seed keeps transfer donors stable across reruns (T5). |
| Trapezoidal integration on irregular timestamps | F02 | Integrate with actual dt per sample pair, `dt·(y₁+y₂)/2`, never a nominal rate; stop at every trace break so dropouts donate nothing (AR-16/F-13). |
| The YAML 1.1 float trap | F02 | `repr(7e-06)` has no dot, so `safe_load` returns a string; scientific notation must be written `7.0e-06` to load back as a float. |
| Byte-deterministic artifacts | F02 | Same data in, identical bytes out: total ORDER BY on every query, sorted keys in the writer, and a data watermark instead of a clock. |
| Point-mass longitudinal model (effective car) | F03 | Car as mass under effective power and drag `m·a = P/v − beta·v²`, both fitted from telemetry so they absorb every unsourced physical constant (T1, 5.4). |
| RK4 ODE integration | F03 | Fourth-order Runge-Kutta solving the point-mass trajectory over distance; four gradient samples per step, error ~step⁵, validated against the flat-out closed form. |
| Frozen train/validation split and data leakage | F03 | Calibrate on 2026 rounds 1–6, validate on 7+ (E-14); leakage is any path by which held-out data reaches a fit, blocked here in three independent layers. |
| Distribution distances (KS, EMD) | F03 | KS is the max gap between two CDFs, EMD the work to reshape one histogram into another (laps for stints); the 5.4.1 sim-to-real metrics. |
| Logistic regression by Newton-Raphson | F03 | Maximum-likelihood fit of a probability model `P(pass) = sigmoid(design·beta)`, iterated to convergence by hand — T7's overtaking model. |
| Derived quantity vs noisy regression | F03 | Computing `c_lc` as an exact slope off the calibrated model (sweep lift depths) instead of regressing confounded race laps. |
| Seeded Monte Carlo with stream spawning | F03 | `SeedSequence(seed).spawn(n)` gives each simulated race an independent reproducible RNG, so validation figures regenerate byte-identically (5.5.5). |
| GLTF / GLB mesh (positions + indices) | F04 | A 3D model as two lists — a flat vertex-position buffer and integer triangle indices into it; GLB packs the glTF JSON and buffer into one binary file the frontend loads (5.10.1). |
| Arc-length resampling | F04 | Re-dropping points at uniform distance along a path (every 2 m) instead of uniform time, so corners and straights get equal point density for smoothing and curvature. |
| Savitzky-Golay filter | F04 | Sliding-window smoothing that fits a low-order polynomial per window and takes its centre value, keeping corner shape while killing GPS noise; Z smoothed harder than X/Y. |
| Frenet vs rotation-minimising frames | F04 | Frenet's normal flips 180° at inflections/hairpins; RMF carries a sideways vector along the curve by parallel transport (double reflection) with minimal rotation, so the ribbon never twists (E-17). |
| Parallel transport and holonomy | F04 | Transport carries a frame forward with least turn; on a closed loop the residual twist (holonomy angle) is measured and spread over all stations so the frame is periodic and the seam is clean. |
| Menger curvature / radius of curvature | F04 | Local radius from three consecutive points, r = (a·b·c)/(4·area); inf on straights, small in hairpins — the ribbon half-width is clamped below it so tight corners cannot fold (5.10.1 item 4). |
| Segment-intersection orientation test | F04 | Two segments cross only if each straddles the other, tested by the sign of the triangle-orientation cross product; shared endpoints give zero and never count, so the loop seam is legal (E-17). |
| Stylised vs sourced provenance (visual data, F-12) | F04 | The anti-black-box rule for pixels: numbers that only change how the track looks (elevation, camber, width) are flagged `stylised` in config and metadata, so the UI never shows decoration as data. |
| Gymnasium environment (reset/step loop) | F05 | An RL env exposing `reset()` and `step(action)` that returns observation, reward, terminated and info; the agent sees only observations and rewards and learns the mapping — SB3 trains against this contract (5.5). |
| MultiDiscrete action space | F05 | Two independent discrete choices picked together, `MultiDiscrete([6, 4])` — a pit head and a mode head — so the structure of "pit and mode are separate decisions" is visible to the agent (5.5). |
| Action masking (legal by construction, F-16) | F05 | A boolean vector per head zeroing illegal actions before sampling, plus physics clipping of continuous limits; together 100% compliance by architecture, with reason codes, not a reward penalty. |
| Scale-bounded observation | F05 | The 32-dim ego vector (5.5.1), every slot named and pre-clipped to about [-1, 1] at encode time, so a served model degrades gracefully if VecNormalize statistics drift. |
| Potential-based reward shaping (telescoping, F-15) | F05 | Shaping `F = gamma x Phi(s') - Phi(s)` with `Phi = -0.1 x position`; provably policy-invariant and sums to zero over any position cycle, killing the oscillation exploit that broke v2. |
| Struct of arrays / hot-loop rule | F05 | Race state as one numpy array per attribute across all 22 cars, not per-car objects, so the field advances in vectorised numpy with nothing pandas-shaped reachable from `step()` (5.6.2). |
| Era switch (A-10) | F05 | One `build_scenario` recipe reading either physics_2026 (synthetic energy integrals) or physics_2024 (MGU-K budget), so the same env code runs both the 2026 race and the 2024 counterfactual. |
