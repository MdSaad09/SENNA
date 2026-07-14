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
