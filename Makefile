# A-09 reproducibility pack. Each stub becomes real in the feature that owns it;
# until then it says so instead of silently doing nothing.
#
# Recipes call `python` directly, so run these inside the project env: either
# `uv run make <target>` (e.g. `uv run make bench`) or activate .venv first.

.PHONY: lock lint migrate ingest fit synth synth-figures circuits bench train eval report

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

# build one GLTF ribbon + metadata per ingested circuit into data/circuits/
# (gitignored). Reads Postgres for the dry-session pick and the FastF1 cache for
# geometry — local only, never CI (needs both). Regenerate after a fresh ingest.
circuits:
	python -m senna.circuits.build

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

eval:
	@echo "not yet: F08 owns make eval"

report:
	@echo "not yet: F14 owns make report"
