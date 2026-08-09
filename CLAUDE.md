# SENNA — project memory for Claude Code

SENNA is a Formula 1 strategy engine built as an MSc dissertation (COMP702, University of
Liverpool). A lap-level simulator races 22 cars under corrected 2026 regulations; a
MaskablePPO agent decides pit stops and energy modes every lap; a SHAP layer explains
every call; a React/R3F dashboard shows it all. The project was specced under an
earlier working name — it is now named SENNA everywhere. Treat any surviving trace of
the old name as SENNA and rename it on sight in prose, docs and UI (the source PDF's
internal text is the only place it may remain). Code identifiers follow the master spec
exactly (the env class stays `F1RaceEnv`, because the spec is the contract).

Owner: Saad. He is learning this stack as we build. Keep chat jargon low, explain
decisions when asked, and never skip the lesson step in /ship.

## Read this first, every session
1. `INDEX.md` — what is done, what is in flight, what comes next. Update it only when a
   workflow command says to.
2. The active feature's spec: `docs/spec/features/Fxx-*.md`.
3. The master-spec sections that feature lists under "Spec anchors" (`docs/spec/*.md`).
4. The local `CLAUDE.md` of any directory you are about to change.

The master specification (v3.0, 7 July 2026, in `docs/spec/source/`) is the contract.
Its audit IDs are cited throughout this repo: F-xx = audit findings, E-xx = edge cases,
R-xx = removals, A-xx = additions, T1–T8 = synthetic-data transformations,
M1–M11 = evaluation metrics, AR-xx = assumptions, OQ-xx = open questions. When a feature
spec cites an ID, read that row in the master spec before writing code against it.

## The workflow (one feature = one session = one branch)

    /plan-feature Fxx   plan only, in plan mode, stop for Saad's approval
    /ship Fxx           branch, tests first, build, subagent reviews, lesson, stop
    /land Fxx           merge --no-ff into main, delete branch, update INDEX.md
    /review             run the review battery on demand
    /teach <target>     write or extend a lesson
    /status             where are we, and what should Saad type next

Hard rules:
- Never commit to `main` except merges via /land and `docs:` commits that touch only
  INDEX.md, docs/plans/, docs/learn/, or the workflow itself (CLAUDE.md, .claude/).
  Workflow maintenance has no feature branch to ride, so it lands on main or nowhere —
  but it is still `docs:`, still small, and never bundled with feature work.
- Never start implementing during /plan-feature. Never merge during /ship.
- Tests are written and shown failing before the code that makes them pass.

## The interpretability contract (Saad's non-negotiable)
Nothing is a black box. An inline constant in code is a defect. Every number lives in
`configs/*.yaml` with a comment naming its origin: `sourced` (document + AR-id),
`fitted` (which notebook produced it), `stylised` (an explicit visual choice), or
`operational` (an engineering default — timeout, page size — with its sizing rationale).
The spec-auditor agent enforces this on every diff — expect it.

## 2026 physics — regressions here fail the viva
| Fact | Correct | Never write |
|---|---|---|
| MGU-K electric power | 350 kW; full to 290 km/h, tapers to 0 at 355 km/h | 400 kW (that is the ICE) |
| Energy store | 4 MJ usable, SOC in [0, 4] | 8 MJ anywhere |
| Per-lap deployment cap | does not exist | any "4 MJ/lap" cap, plane, penalty or metric |
| Harvest cap | per-circuit config, 8.5 MJ baseline (5–9 range) | a hard-coded literal |
| Overtaking aid | Manual Override: gap <= 1.0 s, 350 kW held to 337 km/h | DRS, or aero gated by ERS/gaps |
| Grid | 22 cars, 11 teams (Cadillac) | 20 or 24 hard-coded |
| Fastest-lap point | abolished from 2025 | any fastest-lap action or reward |
| Race fuel | ~70 kg — grade C, VERIFY before Phase 2 | 100 kg in the 2026 era |
| Compliance | action masks + physics clipping: 100% by construction | reward penalties for legality |
| Reward | exactly 3 terms: pace shaping, potential-based position, terminal points | any extra term |
| Data | FastF1 >= 3.7 (Jolpica) + OpenF1 historical (2023+) | Ergast; OpenF1 real-time |

Source of truth: `configs/physics_2026.yaml` and the assumptions register (spec Part 8).

## Repo map
    senna/       Python package: data ingest, physics, env, training, explainability
    api/         FastAPI app + WebSocket streaming (rules in api/CLAUDE.md)
    worker/      RQ worker running the frozen model triplet (created in F10)
    frontend/    React 18 + R3F 8 dashboard, six views (rules in frontend/CLAUDE.md)
    configs/     every constant, with provenance — the anti-black-box artifact
    tests/       pytest, including property tests; slow runs carry markers
    docs/spec/   master-spec sections + one spec per feature
    docs/plans/  approved plans, written by /plan-feature
    docs/learn/  Saad's lessons, written by the teacher agent
    notebooks/   calibration + residual plots, one per fitted module

## Code and git style
- All code follows `.claude/skills/human-code/SKILL.md`. All prose (docs, lessons,
  README, commit bodies) follows `.claude/skills/humanizer/SKILL.md`.
- Conventional commits, imperative mood, lower-case type, no emoji, no AI attribution,
  no Co-authored-by trailers, no "generated" phrasing. Body only when the why is not
  obvious from the diff.
- Branches: `feature/Fxx-short-slug`. Python 3.11. React 18 + R3F 8 — never React 19 /
  R3F 9 (the classic install failure, spec 5.9.1).
- Hot-loop discipline: nothing pandas-shaped reachable from `F1RaceEnv.step()`; the
  5.6.2 throughput gate depends on it.

## Academic integrity
Saad declares AI assistance per the COMP702 policy (spec OQ-3 / F-30). The human-code
and humanizer skills exist for craftsmanship and readability — they never change what
gets declared.
