# The freeze — tagging v1.0.0 and shipping the snapshot

The freeze is the last deliverable (F15, A-09): one tag that pins the model
versions, the config fingerprints, the seed manifest and the data snapshot
together, so "which exact system produced Chapter 7" has a one-word answer. This
file is the runbook; every step runs after `/land F15` merges to main.

## What the tag pins

| Artifact | Value | Where it lives |
|---|---|---|
| Headline model | `senna-ppo-4b557848ff25-C-04177920` | `models/headline/` (committed, baked) |
| Era-matched 2024 model | `senna-ppo-d972ad8448dd-C-05849088` | `models/era2024/` (committed, baked) |
| Surrogates | one per model version | `models/explain/<version>/` (committed, baked) |
| Env config hash | the headline manifest's fingerprint | every suite store envelope |
| Seed manifest | `configs/seeds.yaml` (frozen 19 Jul 2026) | fingerprint in every envelope |
| Data snapshot | `data/snapshot/MANIFEST.md` sha256 | dump on the GitHub release |

`make verify` proves the chain from a clean clone: the committed chapter
regenerates byte-for-byte, every store envelope names the baked manifests, the
live seeds fingerprint matches, and no public page carries a rotten link.

## The steps

1. On main after the merge: `rm -rf .ruff_cache && make lint` (ruff's warm cache
   once hid an import-order error on a tests-first feature), `make test`,
   `make verify`.

   Then the A-09 round-trip, which CI cannot run because it needs the ingested
   store and a warm FastF1 cache, and which is the only check that catches
   committed constants disagreeing with what their own data produces:

        DATABASE_URL=postgresql+asyncpg://senna:senna@localhost:5432/senna \
          python -m pytest tests/physics/fits/test_refit_reproduces_committed.py -m slow

   It skips rather than fails if either is missing, so read the result: three
   skips means the promise went unchecked, not that it held. Since F17 the module
   covers `configs/drivers.yaml` as well as the physics, and reruns the battery
   with both out-paths redirected — a run that wrote back over either committed
   file would pass by overwriting the evidence.
2. `make snapshot` against the ingested store, then commit the regenerated
   `data/snapshot/MANIFEST.md` if it changed (`docs:` commit).
3. Tag, with the pins in the message:

        git tag -a v1.0.0 -m "SENNA v1.0.0 — the COMP702 freeze
        headline senna-ppo-4b557848ff25-C-04177920
        era2024  senna-ppo-d972ad8448dd-C-05849088
        snapshot sha256 <from data/snapshot/MANIFEST.md>
        never-cut list intact: masking, cleaning contract, calibration/validation
        split, metric suite with gaming notes, decision cards (spec 6.3)"
        git push origin main v1.0.0

4. Create the release and attach the dump (no gh on this machine; curl + the git
   credential works):

        TOKEN=$(printf 'protocol=https\nhost=github.com\n' | git credential fill \
                | sed -n 's/^password=//p')
        curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
          https://api.github.com/repos/MdSaad09/SENNA/releases \
          -d '{"tag_name": "v1.0.0", "name": "SENNA v1.0.0", "body": "See data/snapshot/MANIFEST.md for the snapshot digest; docs/freeze.md for what this tag pins."}'
        # with the returned id:
        curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
          -H "Content-Type: application/octet-stream" \
          --data-binary @data/snapshot/<dump-file> \
          "https://uploads.github.com/repos/MdSaad09/SENNA/releases/<id>/assets?name=<dump-file>"

5. Verify the asset: download it fresh and `shasum -a 256` against the manifest.
6. Check the Actions run for the merge commit is green (the standing post-land
   rule — F03–F06 once merged red unnoticed).

## Submission-mechanism caveat (open item, Saad)

If the COMP702 submission is a self-contained bundle rather than repository
access, the snapshot must travel with the bundle or via university storage — a
GitHub release link inside a zip the markers never open online helps nobody.
Saad confirms the mechanism before the freeze; until then the release asset is
the plan of record (decision, 28 Jul 2026).

## What is deliberately NOT frozen

The 12 GB FastF1 HTTP cache stays local — `make ingest` against the snapshot's
season list rebuilds it from the public APIs, slowly. The Railway deploy remains
an unverified runbook (decision, 22 Jul 2026). And the W&B run history is
offline-only; `models/runs.json` is the committed ledger.
