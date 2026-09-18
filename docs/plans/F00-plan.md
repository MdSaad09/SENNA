# F00 — Repo skeleton, CI & spec split — plan

## Context

F00 is the first feature: a repo that runs before it does anything. Local docker compose
brings up postgres, redis, a hello-world FastAPI and a hello-world Vite app; GitHub
Actions runs pytest + vitest + lint on every push; lockfiles freeze the exact stack; and
the master-spec PDF is split into per-section markdown so every later session reads only
what it needs. Dependencies: none — F00 is the root of the ledger. INDEX.md confirms
nothing has to land first.

**Repo reality check (explored):** the repo holds only docs and configs —
no Python, no JS, no CI. The master spec PDF (34 pages) sits in `docs/spec/source/` as
under its old pre-rename filename, untracked. A GitHub remote exists
(`MdSaad09/SENNA`). The machine has **no Docker, no Node, no Python 3.11, no Homebrew**
(only system Python 3.9.6) — see Questions.

## Objective & spec anchors

Ship the Phase 0 skeleton per master spec **Part 6.2 Phase 0** ("docker compose up is
green; CI passes on push; lockfiles committed"), **5.9.1** (pinned stack — pin what
breaks, float what does not), **5.11** (service graph and env variables), and
**docs/spec/README.md** (the extraction contract).

IDs that shaped choices:
- **F-10** — fastf1 pinned `>=3.7,<4`: 3.7+ is the Jolpica-backed line.
- **F-26 / F-27** (via 5.11.2) — env-variable table copied faithfully into compose:
  `DATABASE_URL`/`REDIS_URL` use compose service names (server-side only); `VITE_API_BASE`
  is `/api` behind a vite proxy, never a Docker hostname; `WANDB_API_KEY` never appears
  in serving containers.
- **A-09** — Makefile stubs (`ingest/fit/train/eval/report`) are the reproducibility-pack
  skeleton.
- **5.9.1 install trap** — React 18.3 + R3F ^8.17 + drei ^9 + exact three pin; never
  React 19 / R3F 9.

**Conflicts found (master spec wins, per workflow):**
1. The repo map says `worker/` is "created in F10"; master spec Phase 0 includes
   `worker/` in the folder structure. → Create the `worker/` directory now with a
   README stub; its code lands in F10. Compose gets only the four F00 services
   (postgres, redis, api, frontend); the worker service is added in F10, matching the
   feature spec's "green on all four services".
2. F00's test expects `/api/v1/health` → `{"status": "ok"}`; master spec 5.9.2 says the
   shape is `{status, model_version}`. → Return `{"status": "ok", "model_version": null}`
   — satisfies both (test asserts the `status` key; the 5.9.2 shape exists from day one;
   F10 fills the version).
3. docs/spec/README.md says the PDF should be named `SENNA_Master_Spec_v3.pdf`; the file
   on disk still carries the old project name and is untracked. → Rename and
   commit it as part of this feature (also serves the rename done-means).

## Deliverables

**Scaffolding & packaging**
- `pyproject.toml` — root project metadata (Python 3.11), ruff + pytest config (incl.
  `slow`/`property` markers per the package conventions).
- `requirements.in` + `requirements.txt` — the full pinned stack (5.9.1 table) locked
  with `uv pip compile` (pip-compile-compatible output; see Questions Q2).
- `senna/__init__.py` — package root (version string only; no logic).
- `worker/README.md` — placeholder naming F10 as owner (conflict 1).
- `tests/`, `notebooks/` — created with the first tests / a `.gitkeep`.

**Services**
- `api/main.py` — hello-world FastAPI: `GET /api/v1/health` →
  `{"status": "ok", "model_version": null}`. Nothing else.
- `frontend/` — Vite 5 + React 18.3 + TypeScript scaffold with the full 5.9.1 pin set in
  `package.json` (R3F ^8.17, drei ^9, three exact 0.16x, tailwind 3.4, zustand 4.5,
  @tanstack/react-query 5, recharts 2.12, d3 7, vitest) and `package-lock.json`
  committed. Hello-world App only — no canvas, no views (F11 owns those).
- `docker-compose.yml` — postgres:16-alpine (+ named volume), redis:7-alpine, api
  (Dockerfile.api, port 8000, healthcheck on /api/v1/health, env per 5.11.2), frontend
  (node:20-alpine dev server, port 5173, vite proxy `/api` → `http://api:8000`).
- `Dockerfile.api` — python:3.11-slim, installs from requirements.txt, runs uvicorn.

**CI & reproducibility**
- `.github/workflows/ci.yml` — on push: python job (setup-python 3.11, pip cache,
  install lockfile, `ruff check`, `pytest -m "not slow"`), frontend job (node 20,
  `npm ci`, eslint, `vitest run`).
- `Makefile` — `ingest / fit / train / eval / report` stubs, each echoing "not yet" (A-09).

**Spec split (from the PDF, faithful in meaning, old name→SENNA in prose only)**
- `docs/spec/5.1-architecture.md` … `5.13-recruiter-demo.md` (13 files; `5.5-environment.md`
  is the name master spec 6.1 itself uses). Load-bearing tables carried over intact:
  5.2 constants, 5.5.1 observation vector, 5.5.4 reward, 5.12 metrics.
- `docs/spec/2-edge-cases.md` — Part 2, E-01…E-18 with mechanisms.
- `docs/spec/8-assumptions.md` — Part 8, AR-01…AR-18 with grades.
- `docs/spec/source/SENNA_Master_Spec_v3.pdf` — renamed from the old-name filename, committed.
- `scripts/check_spec_anchors.py` — maps every "Spec anchors" ID in
  `docs/spec/features/*.md` to a file on disk (5.x → `5.x-*.md`, E-xx → `2-edge-cases.md`,
  AR-xx → `8-assumptions.md`; F/A/R/T/M/OQ IDs resolve to the PDF, which Parts 1/3/4/7
  deliberately stay in). Run by pytest and CI.

(PDF text already extracted to the session scratchpad for the split; tables will be
reconstructed against the PDF layout, not paraphrased.)

## Constants & configs

No yaml numbers — **the pins ARE this feature's constants** (feature spec), and they live
in the lockfiles, all `sourced` from master spec 5.9.1:

| Pin | Value | Origin |
|---|---|---|
| Python | 3.11.x | sourced, 5.9.1 |
| fastf1 | `>=3.7,<4` (locks to 3.8.3 today) | sourced, 5.9.1 / F-10 |
| stable-baselines3 + sb3-contrib | **2.9.0 pair** — verified matching minors on PyPI today (11 Jul 2026); re-verify at /ship before locking | sourced, 5.9.1 ("verify at Phase 0, freeze in lockfile") |
| gymnasium | whatever SB3 2.9 resolves | sourced, 5.9.1 |
| torch | `>=2.2,<3`, CPU build | sourced, 5.9.1 |
| pandas / numpy | `>=2.2` / `>=1.26` | sourced, 5.9.1 |
| shap / xgboost | `>=0.45` / `>=2.0` | sourced, 5.9.1 |
| fastapi / uvicorn / pydantic | `>=0.111` / latest / 2.x | sourced, 5.9.1 |
| SQLAlchemy / alembic / asyncpg | 2.0 / 1.13 / 0.29 | sourced, 5.9.1 |
| redis client / rq | 5.x / 1.16 | sourced, 5.9.1 |
| wandb | 0.17+ | sourced, 5.9.1 |
| react + react-dom | 18.3 (never 19) | sourced, 5.9.1 |
| @react-three/fiber / drei / three | ^8.17 / ^9.x / exact 0.16x pin | sourced, 5.9.1 |
| vite / tailwind / zustand / react-query / recharts / d3 | 5 / 3.4 / 4.5 / 5 / 2.12 / 7 | sourced, 5.9.1 |
| postgres / redis images | 16-alpine / 7-alpine | sourced, 5.9.1 / 5.11.1 |

## Tests first

Written and shown failing before any implementation (all fast; **no property tests in
F00** — nothing behavioural exists yet, first property tests arrive with F05):

- `tests/api/test_health.py::test_health_endpoint` — TestClient GET `/api/v1/health`
  returns 200 and `body["status"] == "ok"`.
- `tests/docs/test_spec_anchors.py::test_every_spec_anchor_file_exists` — the check
  script finds a file for every anchor cited by every feature spec (fails before the
  split, passes after — this test drives the extraction).
- `tests/docs/test_spec_anchors.py::test_old_name_absent_from_prose` — no tracked text file
  contains the old project name (enforces the rename done-means; the PDF's internal text is the one
  allowed exception, and its filename is renamed).
- `frontend/src/App.test.tsx` — trivial vitest render: the app mounts and shows the
  SENNA title.
- CI itself is the meta-test: both jobs green on the first push.

## Edge cases handled

No E-xx rows target F00 directly (they start biting at F01). The failure modes F00 does
own, and their mechanisms:
- **The R3F install failure** (5.9.1): React 19 + R3F 9
  drift — prevented by exact/major pins in package.json and the committed lockfile.
- **SB3/sb3-contrib minor mismatch** (5.9.1): MaskablePPO import breaks if minors differ —
  prevented by locking the verified 2.9.0 pair.
- **Spec drift**: a future feature citing a section file that never got extracted —
  prevented permanently by the anchors check running in CI.
- **F-27 foreshadowed**: compose is written with the 5.11.2 env table from day one so no
  Docker hostname can leak into browser config later.

## Acceptance checklist (feature spec "done means")

- [ ] `docker compose up` green on all four services; `/api/v1/health` reachable from the host browser
- [ ] CI green on the first push
- [ ] Lockfiles committed; a fresh clone reproduces the environment
- [ ] All spec section files exist and INDEX.md links resolve
- [ ] No trace of the old project name remains in prose anywhere in the repo

## Out of scope

- Any real ingestion, physics, env or UI code (F01+). No R3F canvas — F11.
- Railway deployment, Dockerfile.worker, worker code, WS streaming — F10.
- Alembic wiring and DB models — land with the first schema (F01's storage), not with an
  empty database.
- The remaining 5.9.2 endpoints and Pydantic response models — F10.
- Parts 1, 3, 4, 6, 7 of the PDF stay PDF-only by design (docs/spec/README.md).

## Questions for Saad

1. **The machine has no toolchain: no Docker, no Node, no Python 3.11, no Homebrew.**
   F00's done-means needs all three locally. Proposed default: you install Homebrew and
   Docker Desktop before /ship (both need your password/GUI — I can hand you the exact
   commands to run with the `!` prefix); the ship session then installs node + uv itself
   and does the rest. Nothing else in this plan changes either way.
2. **Lockfile tool**: master spec says pip-compile. Proposed default: `uv pip compile`
   — same requirements.txt output format, and uv also supplies Python 3.11 without
   Homebrew. Declining this means installing classic pip-tools instead; output is
   identical either way.

## On approval (workflow step 6 — after exiting plan mode)

Save this plan to `docs/plans/F00-plan.md`, set F00 to **Planned** in INDEX.md, commit
both to main as `docs: plan F00`, then Saad types `/ship F00` in this same session.

## Verification (end of /ship)

`docker compose up` then curl `http://localhost:8000/api/v1/health` and open
`http://localhost:5173` from the host; `pytest` and `npx vitest run` green locally;
`python scripts/check_spec_anchors.py` exits 0; a case-insensitive grep for the old
project name over tracked text files returns nothing; push the feature branch (with your approval) and watch both CI jobs go
green on GitHub.
