# F01 — Data ingestion and quality reports

## What we built and why

Everything SENNA will ever claim about tyres, pit losses and safety cars has to be
fitted from real races. F01 gets that raw material into the house: every Race and
Sprint session from 2022 to 2026, pulled once from two public sources (FastF1 backed
by Jolpica, and OpenF1 for pit-stop and stint enrichment), cleaned per the spec's
contract, and stored in Postgres so no later feature ever queries the internet again
(F-10). Think of it as the team's data warehouse the strategists trust before they
model anything.

Two properties matter more than speed. First, resumability: a bulk run takes hours,
upstream services rate-limit you, and your laptop can die mid-flight, so every session
gets a checkpoint and a rerun picks up exactly where the last run stopped (E-12). This
was not theoretical — the very first bulk run was killed by fastf1's own hourly call
budget, and the checkpoint design meant the rerun lost nothing. Second, honesty: a
per-season quality report records what was loaded, what each cleaning rule cost, and
what is missing with a written reason. F02's fits will refuse to run without that
report (F-14). No silent gaps, because a gap you did not notice becomes a biased tyre
model three features later.

One rule shapes the whole schema: store the flagged superset, never a cleaned subset.
In-laps poison pace fits but feed pit-timing fits (E-09), so we keep every lap and
store flags; each fit filters at query time.

The finished run is on main: 121,406 laps from 227 checkpointed session loads (a
Race or Sprint counts once per source), covering every due session across the 115
events on the 2022–2026 calendars, five committed quality reports, completeness
green. And zero exclusions — which surprised us, and the surprise had a lesson in
it (the OpenF1 story below).

## New ideas in this feature

**pandas DataFrames, and NaT vs NaN.** A DataFrame is a table in memory: named
columns, one type per column, fast whole-column operations. FastF1 hands us
DataFrames, so ingest and cleaning live in pandas (and only there — the env hot loop
never touches it). Missing values come in flavours: `NaN` for a
missing number, `NaT` ("not a time") for a missing timestamp or duration. Both are
contagious (arithmetic with them yields more of them) and both answer `False` to
ordinary comparisons, which is why the code reaches for `pd.isna()` instead of
`== None`. A lap with no recorded time arrives as `NaT`, and 5.3.4 says that stays
null in the database — never imputed for fits.

**SQLAlchemy 2.0: ORM models vs Core statements.** SQLAlchemy has two layers. The ORM
layer maps Python classes to tables — `class Lap(Base)` with `Mapped[...]`
annotations *is* the `laps` table, declared once. The Core layer builds SQL statements
as Python objects (`insert(Lap)`, `select(Event.id)`, `delete(...)`) and executes them
on a connection, no Python objects per row. SENNA declares the schema with the ORM and
writes with Core, because bulk-inserting thousands of laps as ORM objects would be
slow ceremony for no benefit. Mental model: the ORM is the blueprint; Core is the
forklift.

**async/await, and why asyncpg forces it.** An `async def` function is a coroutine:
at each `await` it hands control back to the event loop instead of blocking the
thread. Our Postgres driver, asyncpg, only speaks this dialect — every database call
must be awaited from inside a coroutine, started by one `asyncio.run()` at the top.
Why carry that into a batch job? The stack pins exactly one driver (5.9.1): the F10
API must be async, so ingest shares asyncpg rather than dragging in a second, sync
driver just for comfort.

**Alembic migrations, not `create_all`.** `Base.metadata.create_all()` creates
whatever tables are missing and silently ignores everything else — it cannot add a
column to a table that already holds three seasons of laps. Alembic stores schema
changes as ordered, reversible scripts; `alembic upgrade head` replays them, and the
database remembers which revision it is at. F01 already needed this for real: the
review added `sessions.is_dry` and relaxed `openf1_pit_stops.lap_number`, and that
landed as a second migration applied to a database mid-ingest, no data lost. Mental
model: `create_all` is a photo of the schema; migrations are the git history.

**Unique constraints, transactions, and upserts.** A unique constraint is the
database refusing duplicates: `UniqueConstraint("season", "round")` means no second
row may claim 2024 round 1 — Postgres raises rather than complies. A transaction
(`engine.begin()`) makes a group of statements all-or-nothing: either every statement
commits together or none do. An upsert (`INSERT ... ON CONFLICT`) leans on a unique
constraint to say "insert this row, and if it already exists, update it (or do
nothing) instead" — one atomic statement, no read-then-write race. All three carry
real weight in this feature; the constraint even caught a bug for us (see Try it,
exercise 1's warning).

**Token-bucket rate limiting.** A bucket holds up to `burst` tokens and refills at
`rate` tokens per second; each request takes one, and an empty bucket makes you wait
for the next refill. The effect: short bursts are allowed, but the long-run rate never
exceeds the configured one. OpenF1's free tier allows roughly 3 requests per second
(AR-15), and E-12's whole premise is that bulk ingest must never hammer a free
service.

**Test fixtures and injectable clocks.** A pytest fixture is a named builder that
pytest injects into any test that lists it as an argument — `make_laps` builds tiny
DataFrames with FastF1's exact column spellings, so no test touches the network. The
injectable clock is the same idea applied to time: `TokenBucket` takes `clock` and
`sleep` as plain functions, and tests pass a `VirtualClock` whose `sleep` just adds to
a counter. The throttle tests "wait" two virtual seconds and finish in microseconds.
Tests that really sleep are slow and flaky; tests on virtual time are exact.

**Delete-and-reload vs upsert (two idempotency patterns).** Idempotent means running
the job twice leaves the database as if it ran once. Upserting every row works when
every table has a natural key, but `race_control` has none — real feeds repeat
identical messages. So data rows use the other pattern: inside one transaction, delete
everything this session previously stored, reinsert fresh, done. Identity rows
(events, sessions, checkpoints) do use upserts, because two sources share them and
neither may clobber the other. The split is the design decision, not an accident.

**Checkpointed resumable batch jobs.** One database row per unit of work — here,
(season, round, source, session_name) — with a state: `loaded`, `failed`, or
`excluded` with a written reason. The trick that makes it trustworthy: the flip to
`loaded` commits in the same transaction as the data rows, so a kill mid-write rolls
back both and there is no lying checkpoint and no `in_progress` state to repair. A
rerun skips terminal states and retries the rest. This is E-12 turned into a table.

**A 404 that means "no rows".** REST APIs disagree about what an empty result looks
like: most return `200` with `[]`, OpenF1 returns `404 Not Found` for any query that
matches zero rows. Once that dialect is verified, the client must translate the status
back into "zero rows" at exactly the endpoints where an empty answer is legal — and
nowhere else, so a mistyped path still fails loudly. SENNA needs this because excluding
a whole session over one empty endpoint would discard the other endpoint's real rows
and put a false gap in the completeness report (F-14). Mental model: this API answers
"nothing matched" with silence, and the client is the interpreter who knows when
silence is an answer. Smallest example: `client.pit(key)` returns `[]` on a 404, while
`client.get("pit", ...)` still raises.

## The code, guided

### senna/config.py and configs/*.yaml

The one loader for every constant in the system. `load("ingest")` reads
`configs/ingest.yaml`; `get(cfg, "openf1.rate_limit_rps")` walks the dotted path and —
the load-bearing part — raises `NullConstantError` if the value is `null`. A null in
yaml means "not fitted yet", and reading one must be a crash, not a guess. That is the
interpretability contract (provenance comments, F00) with teeth. Stdlib plus PyYAML
only, so the future env hot loop can import it safely.

`configs/ingest.yaml` holds every F01 number with its origin: `rate_limit_rps: 3.0` is
sourced (AR-15), `pos_speed_zscore_max: 4.0` is stylised because 5.3.4 mandates the
outlier gate but names no threshold. `configs/data_split.yaml` is different in kind:
it freezes the 2026 calibration/validation split (rounds 1–6 calibrate, 7+ held out)
with the freeze date, because E-14 says deciding this *after* seeing fits would be
train-test contamination. The file header says exactly that for the viva.

### senna/data/schema.py

Eleven ORM classes, one per table. Mostly declaration, but four lines are decisions:

```python
lap_time_s: Mapped[float | None]  # NaT stays null — never imputed for fits (5.3.4)
```

`| None` makes the column nullable. A lap with no time is stored as a lap with no
time; the honesty lives in the type.

```python
__table_args__ = (UniqueConstraint("session_id", "driver_number", "lap_number", "source"),)
```

`source` is in the laps key because synthetic 2026 rows (F03) will share this table;
real and synthetic laps for the same driver and lap number must coexist.

```python
era: Mapped[str]  # which physics yaml governs this row: "2024" or "2026"
```

Every lap knows which regulation era produced it, so no later query has to infer it
from the season. And `RaceControlMessage` carries a comment explaining its *missing*
constraint: no natural key exists, so idempotency for that table comes from
delete-and-reload, not the database.

### migrations/ and db.py

`migrations/env.py` is Alembic's async template pointed at our metadata — asyncpg is
the only driver, so even migrations run through an async engine. Two revisions exist:
the initial full schema, and the review's `is_dry` / nullable `lap_number` change. CI
runs `alembic upgrade head` *and* `alembic check`, which fails if `schema.py` and the
migrations disagree — drift between the blueprint and the history is caught on push
(CI on push, F00). `db.py` is eight lines: build an engine from `DATABASE_URL`, or
explain exactly how to set it.

### senna/data/throttle.py

The whole algorithm is `acquire`, so line by line:

```python
def acquire(self) -> None:
    self._refill()
    if self._tokens < 1.0:
        self._sleep((1.0 - self._tokens) / self.rate_rps)
        self._refill()
    self._tokens -= 1.0
```

`_refill()` first, because tokens accrue with wall time whether or not anyone asked —
it computes `elapsed * rate` and caps at `burst`. If less than one token remains, sleep
exactly long enough for the deficit to refill: `(1.0 - tokens) / rate` seconds, no
polling loop. Refill again after sleeping so the bookkeeping matches the new time.
Then spend one token. Both `clock` and `sleep` were injected in `__init__`, which is
the entire reason the tests can prove "100 requests never exceed 3/s" without a single
real sleep.

### senna/data/openf1.py

The client resolves its config through `senna.config.get` (a null raises, per the
contract) and routes every request through the bucket. The retry loop:

```python
for attempt in range(self._max_retries + 1):
    self._bucket.acquire()
    response = self._http.get(endpoint, params=params)
    if response.status_code not in RETRYABLE_STATUSES:
        response.raise_for_status()
        return response.json()
    if attempt == self._max_retries:
        response.raise_for_status()
    backoff_s = min(
        self._backoff_base_s * self._backoff_factor**attempt,
        self._backoff_cap_s,
    )
    self._sleep(backoff_s)
```

Every attempt pays a token first — a retry storm must not bypass the rate limit. A
non-retryable status either returns or raises immediately; only 429 and the 5xx family
earn exponential backoff (1 s, 2 s, 4 s... capped at 60), and the last attempt raises
rather than sleeping pointlessly. Above the loop, `year < first_season` raises
`OpenF1YearError` before any network call: OpenF1 has nothing before 2023 (F-11), and
asking would waste the budget to learn what the spec already says.

The two data endpoints wrap `get` in one more translation layer, and it earned its
place the hard way. The plan was written believing OpenF1's pit data simply starts
mid-2023, and when `/pit` 404'd on nine early-2023 sessions, the first bulk run duly
excluded them with the written reason "no upstream data". Then the run kept going and
no-stop sprints 404'd too — sessions that demonstrably exist, where the true answer is
"zero pit stops". And `/stints` was returning rows for the same session keys `/pit`
refused. So the 404 never meant "this session is missing"; it is OpenF1's way of
saying "your query matched no rows". The exclusions were reverted, the client learned
the dialect, and all nine sessions loaded:

```python
def pit(self, session_key: int) -> list[dict]:
    return self._rows_or_empty("pit", session_key=session_key)

def stints(self, session_key: int) -> list[dict]:
    return self._rows_or_empty("stints", session_key=session_key)

def _rows_or_empty(self, endpoint: str, **params) -> list[dict]:
    # openf1 404s a no-row query instead of returning [] — seen on /pit
    # before mid-2023 and for sprints where nobody stopped. Zero rows is
    # an answer, not a failure.
    try:
        return self.get(endpoint, **params)
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return []
        raise
```

Only `pit` and `stints` route through `_rows_or_empty`, because those are the two
endpoints where "no rows" is a legal domain answer; the raw `get` still raises on 404,
so a wrong path cannot masquerade as an empty session
(`test_pit_and_stints_treat_a_404_as_zero_rows` pins both sides). And only 404 is
translated — 429 and the 5xx family keep their retry-then-raise path, because an
outage is not an answer. The first version of this story, "excluded with a written
reason beats silence", was already better than most pipelines manage. The final
version is better: an exclusion is a last resort, and reaching for it over one empty
endpoint would have thrown away the stint rows that endpoint's sibling was happily
serving for the very same sessions.

`match_session` pairs a FastF1 session with OpenF1's `/sessions` row by name and UTC
day, with one day of tolerance — Vegas starts late Saturday local and lands on Sunday
UTC. The first version compared naive dates and the review sent it back.

### senna/data/fastf1_loader.py

The only module allowed to import fastf1. `enable_cache` runs before anything else so
every fetch lands on disk and every retry is free (E-12). `plan_sessions` reads the
event schedule's own `Session1..Session5` columns and keeps the names that appear in
`sessions_to_ingest` from yaml — never a hard-coded name list, because sprint sessions
have been renamed twice already and that is data, not code (E-11). It also re-exports
`RateLimitExceededError` so the orchestrator can catch fastf1's hourly budget without
importing fastf1 itself. `_probe_missing_channels` asks the fastest lap for its car
data and records which of the six expected channels are absent — recorded, never
fatal (F-14). One later arrival lives here too: F02 added `load_car_data`, which
pulls per-driver telemetry straight from the on-disk cache and never touches
Postgres. It is walked in the F02 lesson; it sits in this module because this must
stay the package's only fastf1 import site.

### senna/data/cleaning.py — the 5.3.4 contract

Pure functions: frame in, `(frame, DropCount)` out, no mutation, no config reads
(thresholds arrive as arguments so provenance stays in yaml). This is core domain
logic. The subtlest rule in full:

```python
def flag_green_laps(laps):
    is_green = laps["TrackStatus"].map(lambda status: set(str(status)) == {"1"})
```

FastF1's `TrackStatus` is a digit *string* accumulating every status the lap touched:
`"1"` is green throughout, `"12"` means green then safety car mid-lap. `set(str(x)) ==
{"1"}` is exactly "every digit is 1" — a lap is green only if nothing else ever
happened during it. `.map` applies that per row.

```python
    flagged = laps.assign(is_green=is_green)
```

`assign` returns a new frame with the flag column added — flagged, never dropped,
because non-green laps feed the safety-car event-rate fits (5.3.4, E-09). The
`DropCount` records `rows_flagged`, not `rows_dropped`, and that distinction flows all
the way into the report.

The other rules follow the same shape. `drop_inaccurate` really drops
(`IsAccurate == False` laps are FastF1's own "do not trust this timing" flag).
`split_in_out_laps` returns *two* frames — `PitInTime/PitOutTime` non-null rows leave
the pace frame but come back as the pit-timing frame, E-09's "flag, never destroy" as
a return signature. `impute_laptime_for_replay` exists so the dashboard can draw a
continuous line, fills NaT with the median and flags every filled row; its docstring
says fits never call it. `split_telemetry_gaps` assigns a `trace_id` that increments
wherever the sample gap exceeds 2 s — you may not interpolate across a red flag.
`clean_pos_data` converts decimetres to metres, keeps `OnTrack` rows, and drops points
whose implied point-to-point speed sits beyond 4 sigma (a GPS teleport, not a car).
`is_dry_race` is one line each for rain and red flags; the result persists on the
session row so the report and the fits share one answer.

### senna/data/quality.py

Small on purpose: the `DropCount` dataclass, `report_path(season, dir)` — the exact
function F02's refuse-to-fit gate will call — and a markdown renderer with four
sections (completeness, per-rule counts, missing channels, metadata). One honest
detail: the report states in prose that rule counts do not chain, so nobody sums the
Dropped column.

### senna/data/checkpoints.py

`upsert_state` writes one checkpoint row via `ON CONFLICT DO UPDATE` on the
(season, round, source, session_name) constraint. Note it takes a *connection*, not an
engine: the caller decides the transaction, which is what lets the `loaded` flip share
a commit with the data rows. The gate itself:

```python
missing = [
    session
    for session in expected
    # a NaT date is owed, not forgiven: only a known future date defers a
    # session (E-13); an unknown one must be loaded or excluded explicitly
    if not session["session_date_utc"] > now
    and states.get(key_of(session)) not in (LOADED, EXCLUDED)
]
```

Read the condition carefully: it is `not (date > now)`, not `date < now`. With a NaT
date every comparison is `False`, so `not False` keeps the session in the owed list —
a session whose date we do not know must be loaded or excluded, never quietly skipped.
A genuinely future date defers it, which is how Madrid sits on the 2026 calendar all
summer without failing every run before September (E-13). Anything owed and neither
`loaded` nor `excluded` raises `IncompleteIngestError`, listing each offender. The
`excluded` state and `mark_excluded` did get exercised mid-run — the nine early-2023
sessions spent a day in that state before the 404 turned out to be data (the
openf1.py story above) — but the final ingest ended with all 227 owed loads `loaded`
and the exclusion state empty. The machinery stays, because the gate's answer to a
genuine upstream gap is still a written reason, not silence; it just turned out that
2022–2026 does not contain one.

### senna/data/ingest.py

The orchestrator. `run_ingest` is the resume loop:

```python
terminal = (checkpoints.LOADED, checkpoints.EXCLUDED)
for session in sessions:
    if states.get(checkpoints.key_of(session)) in terminal:
        continue
    try:
        frames = loader(session)
    except fatal:
        raise
    except Exception as err:
        ...upsert_state(conn, session, checkpoints.FAILED, error=repr(err))
        continue
    await _write_session(engine, session, frames)
```

`loaded` is done and `excluded` is a recorded decision — retrying an exclusion would
fail again and overwrite the written reason, so both are terminal; `failed` reruns.
The `fatal` tuple exists for exactly one caller today: fastf1's
`RateLimitExceededError`, its own client-side 500-calls-per-hour budget, which killed
the first real bulk run. That one must stop the batch cleanly (everything done so far
is checkpointed; rerun in an hour), while any other exception is one broken weekend
that must not cost the other hundred sessions: recorded as `failed`, skipped, retried
next run.

`_write_session` is the all-or-nothing heart:

```python
async with engine.begin() as conn:
    event_id = await _upsert_event(conn, session)
    session_id = await _upsert_session(conn, event_id, session)
    for table_name, frame in frames.items():
        ...
        await conn.execute(_delete_stale(table_name, session_id, session))
        if rows:
            await conn.execute(insert(TABLES[table_name]), rows)
    await checkpoints.upsert_state(conn, session, checkpoints.LOADED, ...)
```

One `engine.begin()` wraps everything, so the block commits together or rolls back
together. Events and sessions are upserted because both source passes share them —
and `_upsert_session` only overwrites the keys each pass actually knows (the fastf1
pass brings the channel probe, the openf1 pass its session keys), so neither nulls the
other's work. Data tables are delete-then-insert: `_delete_stale` clears what this
session previously stored (scoped to `source = real_<season>` for laps, so future
synthetic rows survive a reload), then Core `insert(...)` with a list of dicts does
one executemany. The checkpoint flip is the last statement *inside* the transaction —
that single placement is the whole resumability guarantee, and
`test_a_crash_inside_the_write_transaction_leaves_no_partial_state` pins it.

The report queries at the bottom are also where the code review earned its keep:
`_completeness_rows` originally called `.scalars()` on the result. On a Core
connection `.scalars()` yields only each row's first column, so the row unpacking
would have crashed — precisely at the moment the hours-long ingest finished and tried
to write its report. The fix is `.all()` and named attributes. A reviewer reading for
"what happens on the happy path's last step" caught what every unit test missed,
because no test rendered a report from a real connection until then.

The CLI (`_amain`) is plumbing: build the season plan from the schedule, split it into
a fastf1 pass and an openf1 pass (2023+ only), run both, write one report per season,
then `assert_complete` over everything due. `--report-only` skips fetching and
regenerates reports from the database. One filter in it was added by the bulk run
itself:

```python
def _due(expected: list[dict]) -> list[dict]:
    # E-13: only a known future date defers a session — Madrid appears in the
    # plan today but is not owed data until its September weekend. A NaT date
    # stays owed rather than silently vanishing from the completeness gate.
    now = datetime.now(UTC).replace(tzinfo=None)
    return [s for s in expected if not s["session_date_utc"] > now]
```

Early resumes ran `run_ingest` over the whole plan, so every not-yet-raced 2026 round
was attempted, failed (no data exists yet), recorded as `failed`, and retried on the
very next resume — and each doomed attempt spent calls from the same 500-per-hour
fastf1 budget that had already killed run one. The completeness gate never owed those
sessions anything, so the attempts bought nothing and taxed the retries that mattered.
Now both passes receive `_due(sessions)` and the gate receives `_due(expected)`: one
definition of "due", applied at the fetch end and the gate end. Notice it is the same
`not >` comparison as `assert_complete`'s own — a NaT date stays due here too, for the
same E-13 reason.

### tests/

`conftest.py` holds the crafted-frame builders and `VirtualClock`. One trap it
documents: an all-NaT column round-trips through a plain list, otherwise pandas infers
the wrong dtype for it. `test_ingest_resume.py` runs against real Postgres
transactions (skipped without `DATABASE_URL`) and proves the headline claims:
kill-then-rerun equals a clean single run, reingest is idempotent, exclusions are
terminal, the two source passes share a session row without clobbering.

And the guard: `tests/docs/test_dead_service_guard.py` greps every tracked code file
for the name of the dead results service (R-04), assembling the needle at runtime —
`needle = ("erg" + "ast").casefold()`. The first version of this test failed CI on
*its own filename*, because the file was named after the service it banned. A
self-referential test has to keep the needle out of both its content and its name;
hence the split-string trick and the rename. Same pattern as F00's old-name test
(tests as forcing functions, F00), same lesson: when a test scans the repo, remember
the test is in the repo.

## How it connects

```
 Jolpica ──► fastf1 (on-disk cache) ──► fastf1_loader ─┐
                                                       ├─► cleaning ─► ingest ─► Postgres
 OpenF1 ──► token bucket ──► openf1 client ────────────┘      (flags)    │      (superset
                                                                         │       + flags)
                              ingest_checkpoints ◄── one commit per ─────┘
                                     │                session
                                     ▼
                       assert_complete + quality report ──► F02 fits (refuse
                                                            without report, F-14)
```

F01 is the leftmost box of the spec 5.1 pipeline. Downstream: F02 reads laps/weather/
pit tables through the same cleaning functions; F03 writes `synthetic_2026` rows into
the very same `laps` table; F04 reads telemetry through the loader's cache.

## Try it yourself

The bulk ingest is done and its five reports are committed under `docs/data_quality/`:
121,406 laps, 227 session loads, zero exclusions. Read-only queries against `senna`
are always safe.

**The one warning that matters:** the Postgres tests drop and recreate every table in
whatever database `DATABASE_URL` names. Pointed at `senna`, pytest erases the ingested
data. Always use `senna_test` (create it once:
`docker compose exec postgres psql -U senna -d senna -c 'create database senna_test'`).
We learned the adjacent lesson the hard way: a leftover fake "Event 1 Grand Prix" row
from a test run in the dev database collided with real Bahrain 2024 on the
(season, round) unique constraint during the first real ingest. The constraint did its
job — it refused the duplicate — but the fix was separating the databases, not
weakening the constraint.

1. Run the fast suite safely:
   `DATABASE_URL=postgresql+asyncpg://senna:senna@localhost:5432/senna_test pytest tests/data -q`.
   You'll know it worked when the resume tests run (not skip) and `senna` still has
   its data afterwards.

2. Poke the real data read-only. `docker compose exec postgres psql -U senna -d senna`
   then `select season, count(*) from laps join sessions on laps.session_id =
   sessions.id join events on sessions.event_id = events.id group by season order by
   season;` and `select state, count(*) from ingest_checkpoints group by state;`.
   You'll know it worked when the per-season lap counts look like real calendars
   (roughly 20k+ laps a season, 121,406 total), the checkpoint query returns exactly
   one state — `loaded`, 227 rows — and you can explain why neither `failed` nor
   `excluded` survived to the end of the run.

3. Change a config value and predict the effect. Set `openf1.burst: 1` in
   `configs/ingest.yaml`, predict which throttle test still passes and what the
   client's request timing becomes, then run `pytest tests/data/test_throttle.py -q`
   (the tests pin their own constants — check whether your edit even reaches them, and
   why that is). Revert. You'll know it worked when you can say where burst is read
   from in production code versus in tests, and why the tests mirror yaml instead of
   loading it.

4. Break the NaT-is-owed rule. In `checkpoints.assert_complete`, change
   `if not session["session_date_utc"] > now` to `if session["session_date_utc"] < now`
   and run the resume tests against `senna_test`. You'll know it worked when
   `test_completeness_ignores_future_events_but_not_past_gaps` still passes but you
   can explain which real-world case (a schedule row with no date) now slips through
   silently — then revert.

5. Regenerate the reports: `python -m senna.data.ingest --report-only` (with
   `DATABASE_URL` pointed at `senna` — report-only never writes to tables), then diff
   `docs/data_quality/2024/data_quality_report.md` against the committed copy.
   Optionally rerun `make ingest SEASONS="--seasons 2024"` and watch it skip every
   loaded session in seconds. You'll know it worked when the completeness table shows
   every session `loaded` — zero exclusions; the state exists, this run never needed
   it — and the rerun costs no network calls.

## Check yourself

1. A lap arrives from FastF1 with `LapTime = NaT`. Trace what happens to it: what
   lands in Postgres, what the pace fits see, and what the replay view sees.

2. Why does the checkpoint flip to `loaded` inside the same transaction as the data
   rows, and what failure mode would a separate "mark loaded afterwards" step create?

3. Defend this design choice: data tables use delete-and-reload for idempotency
   instead of upserting every row. What forced it, and what does the transaction
   contribute?

4. Defend this design choice: `pit()` and `stints()` translate a 404 into zero rows.
   Is that not swallowing errors — how do you know an outage or a typo'd endpoint
   does not now look like an empty session?

5. `assert_complete` treats a session with an unknown (NaT) date as owed, but a
   session dated next month as not owed. Why are those opposite, when both are "no
   data yet"?

---

### Answers

1. Ingest stores the row with `lap_time_s = NULL` and `lap_time_imputed = False` —
   NaT is never imputed at ingest (5.3.4). A fit filtering through the cleaning
   functions simply never sees a usable time for that lap, and the quality report
   counts it under `lap_time_nat` as flagged, not dropped. Only the replay path calls
   `impute_laptime_for_replay`, which fills the median and sets the imputed flag so
   the dashboard can draw a line while admitting which points are invented.

2. Viva answer: the checkpoint and the rows commit atomically, so the checkpoint can
   never lie — `loaded` implies the rows are really there, absent implies they are
   really not. With a separate mark-afterwards step, a kill between the data commit
   and the mark leaves rows without a checkpoint; the rerun sees "not attempted",
   reloads, and only the delete-and-reload pattern saves you from duplicates — while
   a mark-before-write inverts it into a checkpoint with no data. Same-transaction
   placement deletes the whole failure class and needs no `in_progress` state.

3. Viva answer: upserts need a natural key on every table, and `race_control` has
   none — real feeds repeat identical messages, so no constraint can identify "the
   same row". Delete-and-reload inside one transaction makes reruns idempotent for
   any table shape: the delete and reinsert commit together, so a reader never sees
   the gap and a crash rolls back to the previous complete state. Identity rows
   (events, sessions, checkpoints) still upsert because two source passes must merge
   into one row without clobbering each other's columns.

4. Viva answer: the translation is scoped and verified, not a blanket catch. Only
   the two endpoints where zero rows is a legal domain answer route through
   `_rows_or_empty`; the raw `get` still raises on 404, so a wrong path fails
   loudly, and 429/5xx keep their retry-then-raise treatment because an outage is
   not an answer. The verification: sprints where nobody pitted 404 on `/pit` while
   `/stints` returns rows for the same session_key, which pins the meaning as "no
   matching rows", never "no such session". The alternative — excluding the session
   — was tried first, and it threw away real stint data over one empty endpoint.

5. A known future date is a scheduled fact: the session has not happened, so no data
   can exist and demanding it would make every run before September fail on Madrid
   (E-13). An unknown date is missing information, and missing information must never
   relax a completeness gate — if NaT were forgiven, a malformed schedule row would
   silently exempt its session from ever being ingested. Unknown defaults to owed;
   only positive knowledge defers.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
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
