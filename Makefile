# A-09 reproducibility pack. Each stub becomes real in the feature that owns it;
# until then it says so instead of silently doing nothing.

.PHONY: lock migrate ingest fit train eval report

lock:
	uv pip compile requirements.in -o requirements.txt --universal --python-version 3.11 \
		--extra-index-url https://download.pytorch.org/whl/cpu \
		--index-strategy unsafe-best-match --emit-index-url

migrate:
	alembic upgrade head

# bulk ingest is hours of local wall time — run it here, never in CI (E-12).
# narrow the run with SEASONS="--seasons 2024" or SOURCE="--source openf1".
ingest:
	python -m senna.data.ingest $(SEASONS) $(SOURCE)

fit:
	@echo "not yet: F02 owns make fit"

train:
	@echo "not yet: F07 owns make train"

eval:
	@echo "not yet: F08 owns make eval"

report:
	@echo "not yet: F14 owns make report"
