# A-09 reproducibility pack. Each stub becomes real in the feature that owns it;
# until then it says so instead of silently doing nothing.

.PHONY: lock ingest fit train eval report

lock:
	uv pip compile requirements.in -o requirements.txt --universal --python-version 3.11 \
		--extra-index-url https://download.pytorch.org/whl/cpu \
		--index-strategy unsafe-best-match --emit-index-url

ingest:
	@echo "not yet: F01 owns make ingest"

fit:
	@echo "not yet: F02 owns make fit"

train:
	@echo "not yet: F07 owns make train"

eval:
	@echo "not yet: F08 owns make eval"

report:
	@echo "not yet: F14 owns make report"
