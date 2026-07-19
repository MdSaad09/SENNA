# SENNA — index

Claude: read this file at the start of every session. Update it exactly when the
workflow commands say to: plan approved -> Planned; end of /ship -> In review;
/land -> Done + date + lesson link. Keep "Active" and "Next up" true at all times.

**Active feature:** none — next session: `/plan-feature F08` (its plan must open with
the unfitted-compound mask guard — see the 19 Jul decisions entry below)
**Next up:** F08, then F09

## Feature ledger

| ID | Feature | Depends on | Status | Branch | Lesson |
|----|---------|-----------|--------|--------|--------|
| F00 | Repo skeleton, CI & spec split | — | Done 14 Jul 2026 | feature/F00-repo-skeleton | [F00](docs/learn/F00-repo-skeleton.md) |
| F01 | Data ingestion & quality reports | F00 | Done 15 Jul 2026 | feature/F01-data-ingest | [F01](docs/learn/F01-data-ingest.md) |
| F02 | Physics model fits | F01 | Done 16 Jul 2026 | feature/F02-physics-fits | [F02](docs/learn/F02-physics-fits.md) |
| F03 | Synthetic 2026 generator (T1–T8) | F02 | Done 17 Jul 2026 | feature/F03-synthetic-2026 | [F03](docs/learn/F03-synthetic-2026.md) |
| F04 | Circuit ribbon pipeline | F01 | Done 17 Jul 2026 | feature/F04-circuit-ribbons | [F04](docs/learn/F04-circuit-ribbons.md) |
| F05 | F1RaceEnv: obs, masks, dynamics, reward | F02, F03 | Done 19 Jul 2026 | feature/F05-race-env | [F05](docs/learn/F05-race-env.md) |
| F06 | Rivals, baselines, oracle & throughput | F05 | Done 19 Jul 2026 | feature/F06-rivals-baselines | [F06](docs/learn/F06-rivals-baselines.md) |
| F07 | Training: MaskablePPO + curriculum | F05, F06 | Done 19 Jul 2026 | feature/F07-training | [F07](docs/learn/F07-training.md) |
| F08 | Ablations & headline runs | F07 | Todo | | |
| F09 | Explainability: surrogate, SHAP, cards | F07 | Todo | | |
| F10 | Backend: API, worker, WS, deploy skeleton | F07, F09 | Todo | | |
| F11 | Frontend shell + Views 1–2 | F04, F10 | Todo | | |
| F12 | Views 3–4: Energy, Tyre Surface | F11 | Todo | | |
| F13 | Views 5–6: Live, Counterfactual | F11 | Todo | | |
| F14 | Evaluation suite M1–M11 + counterfactuals | F08, F09 | Todo | | |
| F15 | Demo, docs, reproducibility pack & freeze | F10–F14 | Todo | | |

Statuses: Todo -> Planned -> In review -> Done. Shipping happens inside one session, so
there is no persistent "building" state; if a session dies mid-/ship, the branch holds
the work — resume with `claude --continue`, or start fresh and say
"resume F0x from its branch".

## Decisions log (spec Part 7 answers)
- **OQ-1 name:** SENNA (Saad, 7 Jul 2026). Repo, docs and UI say SENNA; code identifiers
  follow the spec.
- **OQ-2 compute:** MEASURED 19 Jul 2026 (F06 `make bench`, spec 5.6.2): **18,477 env
  steps/s aggregate** (~1,540/worker across 12 SubprocVecEnv workers) on Saad's Mac
  (macOS arm64 / Apple Silicon, 10 cores), random-legal actions with the per-step mask
  fetch on the clock. That puts the 8M-step budget at ~7 minutes and 15M at ~14 —
  comfortably above the ~300 steps/s floor and even the spec's 1,000–4,000 expectation,
  so training is cheap and the F07 3-seed + ablation plans are safe as written. Config
  hash e28c3d83ba10. A GPU is optional (the policy is tiny); note the real training
  hardware here if it differs.
- **OQ-3 deadline & AI policy:** default freeze 17 Nov 2026; AI assistance declared.
  Saad: replace with the real submission date and the written COMP702 policy.
- **OQ-4 … OQ-12:** spec defaults apply until edited here.
- **F06 rival bands (Saad, 19 Jul 2026):** held-out test band extrapolates toward each
  archetype's character; F14 must also run the fixed scripted baselines against the
  test band and frame the result as robustness, not in-distribution generalisation.
  TO-DO before F14's M1 run: sanity-check the stylised rival bands against the real
  ingested pit-lap distributions — M1's headline is provisional until that passes.
- **Paired evaluation pairs on event traces, not raw seeds (19 Jul 2026):** tyre-failure
  and pit-service draws consume RNG variates policy-dependently, so same-seed episodes
  diverge in events after the first different stop; F06's EventTrace is the mechanism,
  F14's M1/A-06 harness must use it.
- **Unfitted-compound mask guard — MUST LAND BEFORE F08's headline runs (F07 ship,
  19 Jul 2026):** the action mask does not forbid pitting onto a compound the circuit
  has no deg fit for; unfitted slicks fall back to identity grip (no wear until the
  cliff), so a training agent can learn e.g. "SOFT at Suzuka never degrades". Fix =
  mask slicks outside scenario.available_compounds. Touches the F05 mask contract
  (F-16), so it opens F08's plan rather than landing as a hotfix. F07's own gates are
  unaffected (Stage A runs Monza solo; the heuristic now shops fitted compounds only).
- **AR-10 race fuel (spec Part 8):** VERIFIED 16 Jul 2026 — the FIA 2026 regs cap fuel
  energy flow at 3,000 MJ/h (energy-based, replacing 100 kg/h) and the race allowance
  works out to ~70 kg with the Advanced Sustainable Fuel spec. Sources: Formula1.com
  2026 regulation explainers; FIA 2026 Technical Regulations issue 8 (24 Jun 2024).
  The assumption stands as written ("about 70 kg, energy-flow limited"); next fits
  session may lift the grade-C flag per the register's close-out rule.

## Timeline anchor (spec Part 6.2, start 8 Jul 2026)
F00 by 11 Jul · F01 by 21 Jul · F02–F04 by 4 Aug · F05–F06 by 25 Aug ·
F07–F08 by 15 Sep · F09 by 22 Sep · F10 by 6 Oct · F11–F13 by 3 Nov · F14–F15 by 17 Nov.
Falling behind? The cut order is spec Part 6.3 — and never cut action masking, the
cleaning contract, the calibration/validation split, the metric suite, or decision cards.

---

# Saad's operating manual

## One feature, start to finish
1. Open a terminal in the repo and run `claude`. Name the session after the feature
   (`/rename F05 race env` if your version supports it; otherwise the first message
   names it well enough).
2. Press Shift+Tab until the input bar shows **plan mode**, then type
   `/plan-feature F05`.
3. Read the plan. Ask about anything unclear — in plain English. Request changes the
   same way. When happy, say **approved** and accept when Claude Code asks to exit
   plan mode.
4. Type `/ship F05`. Claude branches, writes failing tests, builds, gets reviewed by
   the subagents, fixes the findings, writes your lesson, and stops with a ship report.
5. Read the ship report and the new lesson in `docs/learn/`. Run the "try it" commands
   yourself. Ask questions — this is your study time. Request changes, or say
   **approved**.
6. Type `/land F05`. Claude merges to main, deletes the branch, and updates this file.
7. Close the session. Next feature = fresh session. Run `/status` any time you are lost.

## When things wobble
- Context bloated, Claude repeating itself -> `/compact`, or land what is done and
  re-plan the remainder as a follow-up feature.
- Session died mid-build -> `claude --continue`, or a new session with
  "resume F0x from branch feature/F0x-...".
- Tests keep failing -> "re-read the spec anchors for this feature, then explain the
  failure before touching the fix".
- Claude typed a raw number into code -> "move that to configs with a provenance
  comment" (the spec-auditor should have caught it; say so).
- You disagree with a review finding -> you outrank the agents. Tell Claude to record
  the rejection with a one-line reason and move on.
- Claude wants to `git push` -> pushes are deliberately not pre-approved in
  `.claude/settings.json`; approve them when asked.

## What only you can do
Approve plans. Approve ships. Answer the VERIFY items (AR-10 fuel mass, AR-11 fastest
lap — spec Part 8). Put your real OQ-2 hardware and OQ-3 deadline in the decisions log
above. Read your lessons. Everything else is a command.
