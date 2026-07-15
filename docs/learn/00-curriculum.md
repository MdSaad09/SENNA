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
