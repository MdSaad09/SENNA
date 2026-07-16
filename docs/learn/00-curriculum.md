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
