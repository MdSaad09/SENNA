# docs/spec — the contract

`source/` holds the master document: **SENNA Master Implementation Specification v3.0**
(7 July 2026). Saad: drop the PDF in there as `SENNA_Master_Spec_v3.pdf` before running
F00.

F00 splits the PDF's build content into one markdown file per section so later sessions
load only what they need:

- `5.1-architecture.md` through `5.13-recruiter-demo.md` — Part 5, faithful in meaning,
  markdown in form. Do not paraphrase the load-bearing tables (5.2 constants, 5.5.1
  observation vector, 5.5.4 reward, 5.12 metrics) — carry them over intact.
- `2-edge-cases.md` — Part 2, E-01 to E-18, mechanisms included.
- `8-assumptions.md` — Part 8, AR-01 to AR-18, grades included.
- Part 1 findings (F-01 to F-30) and Parts 3–4 stay in the PDF; cite them by ID.

Rename rule: the source document says F1SIP; this project is SENNA. Replace the name in
prose during extraction. Leave code identifiers exactly as specified (`F1RaceEnv` and
friends stay).

`features/` holds one spec per feature, F00–F15 — session-sized slices of the master
spec. Each says what to read, what "done" means, and which tests come first. When a
feature spec and the master spec disagree, the master spec wins, and the disagreement
gets flagged in the plan.
