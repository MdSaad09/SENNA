# F00 — Repo skeleton, CI and the spec split

## What we built and why

Before SENNA can simulate a single lap, the workshop has to exist. F00 is that
workshop: a repository that runs before it does anything useful. `docker compose up`
brings up four services (a database, a queue, a hello-world API, a hello-world
dashboard), one command runs the Python tests, one runs the frontend tests, and GitHub
re-runs both on every push so a broken change can never sneak onto `main` quietly.

The other half of F00 is paperwork with teeth. The master spec arrived as one PDF.
Reading a 700-line PDF every session would be slow and error-prone, so we split its
build-relevant parts into per-section markdown files, and we wrote a test that checks
every spec reference in every feature file actually resolves to a file on disk. The
spec split is not documentation for its own sake: later sessions load only the
sections their feature cites, which keeps each session small and focused.

Nothing in F00 knows anything about Formula 1. That is deliberate. When physics
arrives in F02 and the RL environment in F05, they land in a repo where tests,
reproducible installs and CI already work, so every argument from then on is about
racing, not plumbing.

## New ideas in this feature

The ledger is empty, so everything here is new. Eight ideas, briefly.

**Lockfile: intent vs resolution.** You write what you *want* in one file
(`requirements.in`: "fastf1, version 3.7 or later") and a tool computes the exact
versions of everything, including packages you never asked for, into a second file
(`requirements.txt`). Installing from the second file gives every machine the same
environment. Analogy: a shopping list versus the till receipt. Spec 5.9.1 mandates
this. Smallest example: `fastf1>=3.7` in the intent file becomes `fastf1==3.7.1` plus
40 transitive pins in the lock.

**Pin what breaks, float what does not.** Exact-pin only the packages where a version
mismatch causes real failure (SB3 and sb3-contrib must share a minor version; React 18
must pair with R3F 8). Let everything else float within a safe range so you pick up
bug fixes for free. This is the 5.9.1 rule verbatim.

**Environment markers.** A lockfile line can say "this package, but only on this
platform": `nvidia-nccl-cu12==2.30.7 ; sys_platform == 'linux'`. One lockfile then
serves macOS and Linux CI at once. `uv pip compile --universal` produces these.

**Compose as a tiny distributed system.** `docker-compose.yml` declares services
(containers) on a private network where each service can reach the others by name —
the hostname `postgres` resolves to the database container. Healthchecks let one
service wait for another to be genuinely ready, not merely started. Spec 5.11 defines
our four services.

**The browser boundary (F-27).** The compose network's names exist only inside
Docker. Your browser runs outside it, so any URL that reaches the browser must never
contain a Docker hostname. Server-to-server config may use service names; browser
config must use real, reachable addresses. Spec 5.11.2 is the ruling.

**Tests as forcing functions.** Write the test before the thing it tests, watch it
fail, then build until it passes. The failing test becomes a to-do list you cannot
ignore. In F00 a test literally drove the extraction of fifteen spec files.

**CI (continuous integration).** A robot clone of your machine that checks out every
push, installs from the lockfiles, and runs the test suites. If it disagrees with
your laptop, one of you is lying — usually your laptop, because it has state the
robot does not.

**Provenance comments.** The interpretability contract says no number appears without
its origin. In F00 the "numbers" are version pins, and every pin in
`requirements.in` carries a comment naming the spec row that justifies it.

## The code, guided

### requirements.in — the intent file

This file is small enough, and load-bearing enough, to read line by line.

```
fastf1>=3.7,<4              # 5.9.1 / F-10: 3.7 is the Jolpica-backed line
pandas>=2.2                 # 5.9.1: FastF1 3.7 compatibility floor
numpy>=1.26                 # 5.9.1: FastF1 3.7 compatibility floor
```

FastF1 gets a floor and a ceiling: 3.7 because that is the line backed by Jolpica
(the Ergast replacement, F-10), `<4` because a major bump could change its API under
us. pandas and numpy only get floors — they are FastF1's own requirements restated so
the resolver cannot pick something older than FastF1 tolerates.

```
stable-baselines3==2.9.*    # 5.9.1: pair verified matching minors on PyPI, 11 Jul 2026
sb3-contrib==2.9.*          # 5.9.1: MaskablePPO lives here; minor must match SB3
torch>=2.2,<3               # 5.9.1: policy is tiny, CPU wheels are enough
```

The SB3 pair is the strictest pin in the file, and the comment records *when* the
pairing was verified. sb3-contrib (home of MaskablePPO, our agent's algorithm) tracks
SB3 minor-for-minor; mismatched minors is a known breakage. torch floats within major
version 2 because our policy network is tiny and any recent CPU build runs it.

```
shap>=0.45                  # 5.9.1: TreeSHAP path of spec 5.8
numba>=0.60                 # shap's JIT backend; the floor stops the resolver
                            # backtracking to ancient sdists when numpy floats up
xgboost>=2.0                # 5.9.1: surrogate for TreeSHAP
```

The numba line is a war story frozen into a comment. numba is not something we import
— shap drags it in. During the first `make lock`, numpy floated up to 2.4.6, old
numba releases declare `numpy<some-old-ceiling`, and the resolver did what resolvers
do: it backtracked through years of numba releases hunting for one with no ceiling,
landed on a 2021 source-only release, and that sdist cannot even build on Python
3.11. The fix is one floor: `numba>=0.60` forbids the ancient candidates, so the
resolver reconciles numba and numpy in the modern range. The lesson generalises:
**constrain the tool you can name, not the transitive dependency graph you cannot**.
We did not pin numpy down to appease old numba; we pinned numba up.

The rest of the file (FastAPI, SQLAlchemy, redis, rq, wandb, and the floating dev
tools pytest/httpx/ruff) is the 5.9.1 table transcribed, one comment per line. `rq`
carries `F-26` — the finding that chose the simplest adequate queue.

### requirements.txt and the lock command

Never edit this file; `make lock` regenerates it. The Makefile target shows the
non-obvious flags:

```make
lock:
	uv pip compile requirements.in -o requirements.txt --universal --python-version 3.11 \
		--extra-index-url https://download.pytorch.org/whl/cpu \
		--index-strategy unsafe-best-match --emit-index-url
```

`--universal` produces one lockfile valid on any platform, using environment markers.
The pytorch extra index is war story number two: by default, torch's Linux wheel
pulls the CUDA stack — roughly 3 GB of GPU libraries our CPU-only training will never
touch, downloaded on every CI run and every Railway deploy. Locking against PyTorch's
CPU wheel index instead produces this in the lockfile:

```
torch==2.13.0 ; platform_machine != 'x86_64' and sys_platform == 'darwin'
torch==2.13.0+cpu ; platform_machine == 'x86_64' or sys_platform != 'darwin'
```

Mac gets the normal wheel (Macs have no CUDA builds anyway); Linux gets the explicit
`+cpu` build. War story three has no fix: `nvidia-nccl-cu12==2.30.7 ; sys_platform ==
'linux'` is xgboost's doing — its Linux wheel hard-requires the NVIDIA collective
communications library whether or not a GPU exists. We carry the ~200 MB and know why
it is there, which beats not knowing.

### pyproject.toml — one line that saved CI

Mostly boilerplate: project metadata, ruff config, pytest markers reserved for later
features. One line earns a story:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# bare `pytest` (CI) must resolve api/ and senna/ the same way `python -m pytest` does
pythonpath = ["."]
```

`python -m pytest` puts the current directory on Python's import path;
bare `pytest` does not. Locally we happened to run the former, CI ran the latter, and
CI failed with `ModuleNotFoundError: api` on code that passed locally.
`pythonpath = ["."]` makes both invocations identical. Any time CI and your laptop
disagree, hunt for exactly this kind of implicit difference.

### api/main.py and its test

The whole API is ten lines, but even hello-world carries a spec decision:

```python
@app.get("/api/v1/health")
def health():
    # 5.9.2 response shape from day one; model_version stays null until F10
    # bakes the first frozen model triplet into the worker image
    return {"status": "ok", "model_version": None}
```

Spec 5.9.2 defines the health response as including `model_version`. We could have
returned `{"status": "ok"}` and added the field in F10. Instead the shape ships
correct from day one with a null, and the comment names the feature that fills it —
so nobody later "discovers" the field is missing, and the frontend can code against
the final shape immediately. `tests/api/test_health.py` asserts both the status and
the presence of `model_version`, using FastAPI's `TestClient`, which calls the app
in-process — no server, no network, milliseconds per test.

### scripts/check_spec_anchors.py — the test that built fifteen files

Every feature spec has a line like `Spec anchors: master spec 5.9.1, 5.11, F-27`.
This script resolves each cited ID to the file that should contain it. It is F00's
closest thing to domain logic, so here is the core, line by line.

```python
SECTION = re.compile(r"\b5\.(\d+)(?:\.\d+)?\b")
IDS = re.compile(r"\b(AR|OQ|E|F|A|R)-\d+\b")
PDF_ONLY = re.compile(r"\b[TM]\d+\b|\bPart \d\b")
LITERAL_PATH = re.compile(r"\bdocs/spec/\S+?\.md\b")
```

Four patterns, one per kind of citation. `SECTION` captures the section number from
`5.9` or `5.9.1` — the subsection group `(?:\.\d+)?` matches but is not captured,
because `5.9.1` lives in the file for section 5.9. `IDS` catches the audit IDs
(`E-16`, `AR-04`, ...). `PDF_ONLY` catches transformation/metric IDs (`T3`, `M7`) and
bare `Part n` references, which by design stay in the source PDF. `LITERAL_PATH`
catches specs that cite a markdown file outright.

```python
ID_HOMES = {
    "E": "docs/spec/2-edge-cases.md",
    "AR": "docs/spec/8-assumptions.md",
    "F": PDF,
    ...
}
```

This dict is the extraction contract from `docs/spec/README.md` as code: edge cases
were extracted to one file, assumptions to another, findings stay in the PDF. If the
contract changes, this dict is where the change lands.

```python
for section in SECTION.findall(line):
    targets.add(f"docs/spec/5.{section}-*.md")
```

Section citations become glob patterns, because the files carry slugs
(`5.9-stack-and-backend.md`) and the citation only knows the number. Then
`missing_anchor_files` walks `docs/spec/features/F*.md` (the `F` prefix keeps
`_TEMPLATE.md` out), collects targets from each `Spec anchors:` line, and reports any
target that `glob` cannot find. Here is the forcing-function part: this script and
its test were written *first*, when `docs/spec/` held only the PDF. The failure list
was, precisely, the fifteen files to extract. The test was the work order.

### tests/docs/test_spec_anchors.py — the self-referential twist

The second test in that file enforces the rename rule: the project's old working name
must not appear in prose or filenames anywhere outside the source PDF's own text.
Which raises a puzzle — a test that greps every tracked file for a banned string will
find the string *in its own source code*. The fix:

```python
old_name = ("f1" + "sip").casefold()
```

The needle is assembled at runtime from two halves, so the test file passes its own
scan. `casefold()` came out of review: the first version was case-sensitive and would
have waved the old name through in any mixed-case spelling. (First drafts of this very
lesson tripped the test by writing one out as an example. The test won.) The test walks `git ls-files` (tracked files only, so
`.venv` and `node_modules` are never scanned), checks filenames and contents, skips
inside `docs/spec/source/` for content but still checks names there — a PDF dropped
into `source/` must arrive pre-renamed. This one test forced rewording in four files
and a file rename during F00. Cheap test, real work done.

### docker-compose.yml — four services, two rules

Block by block. postgres and redis are stock Alpine images with healthchecks; the
postgres password carries a comment marking it local-only (Railway injects real
credentials, 5.11.2). The interesting decisions are in the api and frontend blocks.

```yaml
  api:
    environment:
      # service names are fine here: these values never reach a browser (5.11.2, F-27)
      DATABASE_URL: postgresql+asyncpg://senna:senna@postgres:5432/senna
    depends_on:
      postgres:
        condition: service_healthy
```

`@postgres:` is a Docker hostname, and it is legal here because the API talks to the
database server-to-server, inside the compose network. The comment cites F-27 so
nobody pattern-matches this into browser config later. `condition: service_healthy`
means the API container does not even start until postgres answers `pg_isready` —
without it, compose starts containers in dependency order but does not wait, and the
API would boot into connection refused.

```yaml
  frontend:
    volumes:
      - ./frontend:/app
      # masks the host's mac-native node_modules; the container installs its own
      - /app/node_modules
    environment:
      VITE_API_BASE: /api
      API_PROXY_TARGET: http://api:8000
```

The volume pair is the node_modules trick. The first line mounts your source into the
container so edits hot-reload. But your host `node_modules` contains binaries
compiled for macOS, and the container is Linux — esbuild would crash on the wrong
binary. The second line, an anonymous volume, shadows just the `node_modules` path
inside the mount, so the container's own `npm ci` output lives there and the Mac
binaries never leak in.

The two environment lines are F-27 in miniature. `VITE_API_BASE: /api` is what the
browser sees: a relative path, valid anywhere. `API_PROXY_TARGET: http://api:8000`
contains a Docker hostname, but it configures the Vite dev server's proxy, which runs
inside the network — see `frontend/vite.config.ts`, where the comment repeats the
ruling. The browser asks Vite for `/api/...`; Vite forwards to `api:8000`
server-side. The browser never learns the Docker name.

`Dockerfile.api` is standard slim-Python fare with one earned line: `libgomp1` is
installed because xgboost's Linux wheel needs an OpenMP runtime that slim images do
not ship.

### frontend/package.json — the same lockfile story in JavaScript

```json
"@react-three/fiber": "^8.17.10",
"react": "18.3.1",
```

React is pinned *exactly*, no caret. R3F 8 pairs with React 18; npm's default caret
range would happily float React to 19 on some future install, and React 19 with R3F 8
is the classic install failure named in spec 5.9.1 and in `frontend/CLAUDE.md`.
Everything else carets within a major. `package-lock.json` (7,000 generated lines —
never hand-edit) freezes the whole tree, and CI installs with `npm ci`, which obeys
the lock exactly and fails loudly if `package.json` and the lock disagree.

### .github/workflows/ci.yml — the meta-test

Two independent jobs, `python` and `frontend`, so a lint failure in one does not hide
results from the other. Both cache their package downloads keyed on the lockfiles —
which only works *because* the lockfiles exist; the cache key is the lock's hash.
The Python job is install, `ruff check`, `pytest -m "not slow"` (the slow marker is
reserved now so training tests can be excluded later without config churn). One
frontend step deserves its sentence:

```yaml
      - run: npx tsc -b
```

Vite's dev server strips types without checking them — a type error that would fail a
production build sails through `npm run dev` silently. CI runs the TypeScript
compiler explicitly so type errors surface on push, not at deploy time.

## How it connects

F00 builds the outer frame of the spec 5.1 architecture. Everything later slots into
a box that already exists:

```
 your browser ──── localhost:5173 ───┐          localhost:8000
      (outside the network, F-27)    │               │
  ┌──────────────── docker compose network ──────────┼──────────┐
  │                                  │               │          │
  │   frontend (vite) ── /api proxy ──► api (fastapi/uvicorn)   │
  │        F00: hello page              F00: /api/v1/health     │
  │                                      │            │         │
  │                             postgres:5432    redis:6379     │
  │                             (F09: results)   (F10: queue)   │
  └─────────────────────────────────────────────────────────────┘

  requirements.in ──make lock──► requirements.txt ──► Dockerfile.api, CI
  docs/spec/source/*.pdf ──F00 split──► docs/spec/*.md ◄── check_spec_anchors
```

## Try it yourself

1. Run `make train`, then predict what `make eval` prints before running it. Check
   the Makefile to see the A-09 pattern: stubs that name their owner instead of doing
   nothing. You'll know it worked when both commands print "not yet:" with the right
   feature number.

2. Break the rename test. Put the old project name (lowercase, one word) into any
   tracked markdown file, run `.venv/bin/pytest tests/docs/`, and read the failure —
   note that the assertion message lists the offending path. Revert. You'll know it
   worked when `test_old_name_absent_from_prose` fails naming exactly your file, and
   passes again after the revert.

3. Break the anchor checker. Add `5.99` to the `Spec anchors:` line of any
   `docs/spec/features/F*.md`, run `python scripts/check_spec_anchors.py`, and check
   the exit code with `echo $?`. Revert. You'll know it worked when the script prints
   `docs/spec/5.99-*.md (cited by ...)` and exits 1.

4. Watch a healthcheck matter. With `docker compose up` running, run
   `docker compose stop postgres`, then curl
   `http://localhost:8000/api/v1/health`. It still answers — the health route
   touches no database yet. Now run `docker compose ps` and look at the api
   container's health column, then restart postgres. You'll know it worked when you
   can explain why health stayed ok while a dependency was down.

5. Practise tests-first. Add an assertion to `tests/api/test_health.py` that the
   response contains `"service": "senna"`. Run pytest and watch it fail. Then edit
   `api/main.py` to make it pass, and revert both (the 5.9.2 shape is the contract —
   this field is not in it). You'll know it worked when you saw the red-then-green
   cycle in that order.

## Check yourself

1. Why does the repo have both `requirements.in` and `requirements.txt`, and which
   one do you edit?

2. The resolver once picked a numba release from 2021. What caused that, and why was
   the fix `numba>=0.60` rather than pinning numpy?

3. `DATABASE_URL` contains the hostname `postgres`, and `VITE_API_BASE` is `/api`.
   Why may the first contain a Docker service name while the second must never?

4. Defend this design choice: react is pinned to exactly `18.3.1` while pandas floats
   at `>=2.2`. Isn't that inconsistent?

5. `npm run dev` works on a file with a type error, but CI fails on it. Which CI step
   catches it, and why does the dev server miss it?

---

### Answers

1. `requirements.in` states intent — the packages we chose, with the loosest safe
   version ranges and a provenance comment per line. `requirements.txt` is the
   machine-computed resolution: exact versions for everything, transitives included,
   with platform markers. You edit only the `.in` file; `make lock` regenerates the
   lock. Editing the lock by hand would be overwritten and would hide the reasoning.

2. numpy floated up to 2.4.6, and recent-old numba releases cap numpy below that. The
   resolver backtracked through numba's history looking for a release with no cap and
   found a 2021 sdist that cannot build on Python 3.11. Pinning numpy would have
   frozen a healthy package to appease a broken candidate set; the floor on numba
   forbids the broken candidates directly. Constrain the package that is actually
   misbehaving, not its neighbours.

3. Viva answer: Docker service names only resolve inside the compose network, and the
   browser runs outside it (F-27, spec 5.11.2). `DATABASE_URL` is consumed by the API
   container, server-side, inside the network; `VITE_API_BASE` is baked into the
   JavaScript bundle and executed in the user's browser, so it must be a
   browser-reachable path or URL — a Docker hostname there fails the moment anyone
   who is not the compose network itself loads the page.

4. Viva answer: the pin policy is risk-based, not uniform — pin what breaks, float
   what does not (5.9.1). React 18 to 19 is a known, certain breakage with R3F 8, so
   it gets an exact pin; pandas within 2.x has no such known break for our usage, so
   it floats and picks up fixes. Consistency of *policy*, not of syntax.

5. `npx tsc -b` catches it. Vite's dev server uses esbuild, which strips TypeScript
   types for speed without checking them, so type errors do not surface until a real
   compile. CI runs the actual TypeScript compiler so the error appears on push
   instead of at build/deploy time.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

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
