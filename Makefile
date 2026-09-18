# A-09 reproducibility pack — every target is real. The pipeline, in dependency order:
#   ingest -> fit / synth -> train / headline -> explain -> finetune ->
#   eval (the M1-M11 suite) -> sensitivity / sensitivity-m2 -> report
# plus the pack around it: snapshot / restore (the frozen data), verify (what a clean
# clone can prove), test / lint (CI's gates, locally), up (the whole stack), and the
# demo warm-up demo-warm. Targets that need the ingested Postgres store or
# the frozen models say so in their comments and never run in CI.
#
# Recipes call `python` directly, so run these inside the project env: either
# `uv run make <target>` (e.g. `uv run make bench`) or activate .venv first.

.PHONY: lock lint test migrate ingest fit synth synth-figures bench train ablate headline rescore eval explain finetune suite archetypes robustness sensitivity sensitivity-m2 snapshot restore verify report demo-warm api app up

lock:
	uv pip compile requirements.in -o requirements.txt --universal --python-version 3.11 \
		--extra-index-url https://download.pytorch.org/whl/cpu \
		--index-strategy unsafe-best-match --emit-index-url

# lint the whole repo exactly as CI does (ruff check .), notebooks included, so the
# local gate can't drift from CI — the cause of the F03-F06 red-CI streak. Notebook
# style rules (E501/E702) are relaxed in pyproject's per-file-ignores.
lint:
	ruff check .

migrate:
	alembic upgrade head

# bulk ingest is hours of local wall time — run it here, never in CI (E-12).
# narrow the run with SEASONS="--seasons 2024" or SOURCE="--source openf1".
ingest:
	python -m senna.data.ingest $(SEASONS) $(SOURCE)

# the full battery reads Postgres + the FastF1 cache and rewrites
# configs/physics_params.yaml — local only, never CI. Narrow with
# ONLY="--only energy" or CIRCUIT="--circuit monaco_grand_prix"
# (narrowed runs skip the yaml write).
fit:
	python -m senna.physics.fits.run $(ONLY) $(CIRCUIT)

# the T1-T8 generator reads Postgres + the FastF1 cache and rewrites
# configs/transforms.yaml (and fills the c_lc/c_atk/p_der block in
# physics_2026.yaml) — local only, never CI. Narrow with ONLY="--only aero"
# or CIRCUIT="--circuit monaco_grand_prix" (narrowed runs skip the yaml write).
synth:
	python -m senna.physics.synth.run $(ONLY) $(CIRCUIT)

# regenerate the 5.4.1 Chapter 6 validation figures + docs/synth/validation_summary.yaml
# from the held-out 2026 rounds (7+). Reads rounds 7+ through heldout.py only (E-14).
synth-figures:
	python -m senna.physics.synth.validate

# measure env steps/s across workers — the 5.6.2 number that prices the training plan.
# narrow with WORKERS=8 or STEPS=50000; record the result and hardware in INDEX (OQ-2).
bench:
	python -m senna.bench.throughput $(if $(WORKERS),--workers $(WORKERS)) $(if $(STEPS),--steps $(STEPS))

# train the curriculum A->B->C (F07, spec 5.6.1/5.7): MaskablePPO, competence gates,
# triplet checkpoints under models/, gate values in curriculum_gates.json. Narrow with
# SEED=211, FROM=B RESUME=models/<run>/stageA/final, STEPS=5000 (dev cap, smoke only),
# WANDB=offline|disabled, WORKERS=2 VEC=dummy. Local only — training never runs in
# serving (F-26).
train:
	python -m senna.train.run $(if $(SEED),--seed $(SEED)) \
		$(if $(FROM),--from-stage $(FROM)) $(if $(TO),--to-stage $(TO)) \
		$(if $(RESUME),--resume $(RESUME)) $(if $(STEPS),--total-steps $(STEPS)) \
		$(if $(WORKERS),--workers $(WORKERS)) $(if $(VEC),--vec $(VEC)) \
		$(if $(WANDB),--wandb-mode $(WANDB))

# one 5.6.3 ablation arm, Stage C from scratch at the 4M ceiling (F08). RUN= names
# the arm in configs/ablations.yaml; SEED= defaults to the first ablation seed.
# DRY=1 proves the wiring on the tiny profile before any real run. Run arms one at
# a time: the ledger is a single file and each run wants every core anyway. Local only.
ablate:
	python -m senna.train.ablate --run $(RUN) $(if $(SEED),--seed $(SEED)) \
		$(if $(DRY),--dry-run) $(if $(WANDB),--wandb-mode $(WANDB)) \
		$(if $(WORKERS),--workers $(WORKERS)) $(if $(VEC),--vec $(VEC))

# the 3-seed headline (F08): full curriculum per seed, cross-seed selection on
# validation points, promotion to models/headline — the model version F09/F10
# consume. SEED= narrows to one seed (no selection); completed seeds are skipped
# via models/runs.json.
headline:
	python -m senna.train.headline $(if $(SEED),--seed $(SEED)) \
		$(if $(WANDB),--wandb-mode $(WANDB)) $(if $(WORKERS),--workers $(WORKERS)) \
		$(if $(VEC),--vec $(VEC))

# re-score a run's selected checkpoint on the validation banks (F08) and note the
# result in the ledger. RUN=models/<run_dir>. This was `make eval` until F15: the
# A-09 pack promises `make eval` = the evaluation suite, and a name that quietly
# meant "one checkpoint's rescore" would hand an examiner the wrong artifact.
rescore:
	python -m senna.train.selection --rescore $(RUN)

# the A-09 name for the M1-M11 battery: `make eval` is what the spec's pack
# enumerates (5.11), and it must mean the thing an examiner expects
eval: suite

# distill the frozen headline triplet, gate on fidelity, and card every validation
# race into agent_decisions (F09, spec 5.8). Reads models/headline + Postgres —
# local only, never CI. Smoke the wiring with PAIRS=2000 RACES=2 SKIP_PERSIST=1.
# OMP_NUM_THREADS=1: torch + xgboost in one process carry duplicate OpenMP runtimes
# on arm64 and segfault without it (F09 plan).
# TRIPLET=models/era2024 ERA=2024 distills and cards the era-matched model on its
# own physics (F-24) — the pair must agree, and the CLI refuses a mismatch.
explain:
	OMP_NUM_THREADS=1 python -m senna.explain.run $(if $(PAIRS),--pairs $(PAIRS)) \
		$(if $(RACES),--card-races $(RACES)) $(if $(SKIP_PERSIST),--skip-persist) \
		$(if $(TRIPLET),--triplet $(TRIPLET)) $(if $(ERA),--era $(ERA))

# local serving against compose postgres (F10). `make api` migrates first and reloads
# on edit; `make app` is the Streamlit interface, which talks to the API over HTTP.
# Source .env (or export DATABASE_URL) before either. There is no worker and no queue:
# a race runs inside the request that asks for it.
api:
	python -m alembic upgrade head
	python -m uvicorn api.main:app --reload --port 8000

# PYTHONPATH=.: streamlit puts the SCRIPT'S directory on sys.path, not the working
# directory, so `from app import client` dies without it — the same hole F24 patched
# in Dockerfile.api with ENV PYTHONPATH=/app. AppTest never sees it (pytest injects
# the root), which is why only running the real thing finds it.
app:
	PYTHONPATH=. streamlit run app/Home.py --server.port 8501

# everything at once: postgres, api, streamlit
up:
	docker compose up --build

# the era-matched Stage C fine-tune (F-24 / OQ-9): warm-starts models/headline onto the
# 2024 constants and promotes the result to models/era2024. Needs the frozen headline.
# DRY=1 proves the wiring on a tiny budget in seconds.
finetune:
	OMP_NUM_THREADS=1 python -m senna.eval.finetune $(if $(SEED),--seed $(SEED)) \
		$(if $(DRY),--dry-run) $(if $(WORKERS),--workers $(WORKERS)) $(if $(VEC),--vec $(VEC))

# roll every M1-M11 battery on the held-out seeds and rival band (5.12) and rewrite both
# stores. Local only: needs models/headline. ONLY=m1,m4 narrows; SMOKE=1 does two circuits.
suite:
	OMP_NUM_THREADS=1 python -m senna.eval.run $(if $(ONLY),--only $(ONLY)) $(if $(SMOKE),--smoke)

# the E-02 harvest-cap robustness pass: rolls the frozen agent at the cap it trained
# under and at the FIA's refined figure, on the same seeds, and writes the store row the
# report renders. CIRCUITS= narrows it (a subset writes to store/subset, never the root).
# the three-archetype view of the published metrics (a slice, never a re-run) and the
# decision-level robustness arms. archetypes needs only the committed store; robustness
# needs models/headline because it races the frozen agent under perturbed physics.
archetypes:
	python -m senna.eval.archetypes

robustness:
	OMP_NUM_THREADS=1 python -m senna.eval.robustness --seeds $(if $(SEEDS),$(SEEDS),20)

sensitivity:
	OMP_NUM_THREADS=1 python -m senna.eval.sensitivity $(if $(CIRCUITS),--circuits $(CIRCUITS))

# the M2 borrowed-coefficient pass (F15): re-rolls the ten counterfactual races with
# the borrowed 2026 energy-mode fit at +/-50% (configs/eval.yaml). Needs the ingested
# Postgres store and models/era2024 — local only, never CI.
sensitivity-m2:
	OMP_NUM_THREADS=1 python -m senna.eval.coefficients

# regenerate the Chapter 7 tables and figures from the committed store. A pure function of
# docs/results/F14/store — no model, no database, no GPU — so a clean clone can rerun it.
report:
	python -m senna.eval.report

# CI's fast suite, locally and by the same spelling — `pytest -m "not slow"` scoped the
# way ci.yml runs it, so the local gate can't drift from CI (the F03-F06 lesson).
#
# Same spelling is not the same environment. ci.yml exports DATABASE_URL for its
# postgres service; without it the API suite skips itself and the run still reports
# green. F18 merged red that way — 55 skips locally, a real failure in CI. Export it
# before trusting this as a gate:
#   DATABASE_URL=postgresql+asyncpg://senna:senna@localhost:5432/senna_test make test
# A green run with skips is not a green run; check the skip count against CI's.
# two invocations on purpose. Streamlit's AppTest leaves its script runtime installed
# in the process, and a SubprocVecEnv spawned afterwards re-executes a page in the child
# — which shows up as the throughput bench dying on an EOFError with a page script
# calling the API behind it. Isolating the page tests is cheaper and clearer than
# fighting Streamlit's teardown, and running them here means they cannot be forgotten.
test:
	python -m pytest -m "not slow" -q --ignore=tests/app
	python -m pytest -m "not slow" -q tests/app

# freeze the ingested store (A-09): pg_dump to data/snapshot/ (gitignored) and rewrite
# the committed MANIFEST.md — sha256, size, per-table counts. The dump rides the tagged
# GitHub release as an asset. Local only: needs Postgres and pg_dump on PATH.
snapshot:
	python -m senna.data.snapshot

# load a snapshot back — only into a database require_disposable accepts (*_test, or
# the named escape hatch). DUMP=data/snapshot/<file>.dump
restore:
	python -m senna.data.snapshot --restore $(DUMP)

# what a clean clone can prove without models or a database: the committed chapter
# regenerates byte-for-byte, the freeze chain is internally consistent, and no public
# page carries a rotten link. CI runs this same target (F15 gate).
verify:
	python -m pytest tests/eval/test_freeze.py -q
	python scripts/check_links.py README.md INDEX.md docs/freeze.md \
		docs/demo/script.md data/snapshot/MANIFEST.md

# pre-run the demo simulations against the local stack so the 5.13 deep link opens
# mid-race instead of blocking on a cold simulation (E-15: the warm run IS the run)
demo-warm:
	./scripts/warm_demo.sh
