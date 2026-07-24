# SENNA — index

Claude: read this file at the start of every session. Update it exactly when the
workflow commands say to: plan approved -> Planned; end of /ship -> In review;
/land -> Done + date + lesson link. Keep "Active" and "Next up" true at all times.

**Active feature:** F12 — in review; next: read the lesson, then `/land F12`
**Next up:** F13, then F14

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
| F08 | Ablations & headline runs | F07 | Done 19 Jul 2026 | feature/F08-ablations | [F08](docs/learn/F08-ablations.md) |
| F09 | Explainability: surrogate, SHAP, cards | F07 | Done 21 Jul 2026 | feature/F09-explainability | [F09](docs/learn/F09-explainability.md) |
| F10 | Backend: API, worker, WS, deploy skeleton | F07, F09 | Done 22 Jul 2026 | feature/F10-backend-serving | [F10](docs/learn/F10-backend-serving.md) |
| F11 | Frontend shell + Views 1–2 | F04, F10 | Done 23 Jul 2026 | feature/F11-frontend-views-1-2 | [F11](docs/learn/F11-frontend-views-1-2.md) |
| F12 | Views 3–4: Energy, Tyre Surface | F11 | In review | feature/F12-views-energy-tyre | |
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
- **F08 headline model (19 Jul 2026):** `senna-ppo-6b6edb78d84e-C-00835584` (seed 331,
  step 835,584, 6.517 validation points) promoted to `models/headline/` — the frozen
  checkpoint F09 explains and F10 serves. Evidence: docs/results/F08-ablations.md;
  ledger models/runs.json. W&B runs are offline pending an account.
- **F09 fidelity badge (21 Jul 2026):** the surrogate that explains the headline model
  agrees with it on **99.70%** of held-out pit decisions and **99.08%** of energy-mode
  decisions, gate 0.90 (spec 5.8.2). Gradient cross-check on the true network: mean
  Spearman 0.687 over 500 decisions, all positive. 14,460 cards across the 240
  validation races sit in `agent_decisions`. Evidence: docs/results/F09-explainability.md.
  A retrain invalidates all of it by construction (E-15) — `make explain` must re-run
  before F10 serves a new checkpoint.
- **Railway deploy deferred (Saad, 22 Jul 2026):** 5.11.1's public deploy is not
  executed. The dissertation deliverable is a reproducible codebase plus the
  presentation video, so `docker compose up --build` is the supported target — a
  marker can run the full stack from a clean clone, which is why the frozen triplet,
  surrogate and ribbons are committed. The serving layer stays deployment-ready
  (Dockerfile.api, start scripts, migrate-on-start, docs/deploy.md) but that runbook
  is now unverified in production and says so. Revisit only if a live URL is wanted
  before the viva.
- **F10 spec divergences (22 Jul 2026):** seven deliberate, recorded with their
  resolutions in docs/plans/F10-plan.md ("Flagged spec divergences") — the E-15 cache
  key gains a scenario digest (the literal 5.9.3 key collides circuits), rival_band
  passed explicitly, frames in a lap_frames JSONB table, era-2024 fields 20 cars,
  cards ride sim:lap (no agent:decision event), local WS is ws://localhost:8000/ws
  (no /ws proxy), one Dockerfile with two start commands. Also new: the fourth
  provenance origin `operational` (configs/README.md) for stated engineering defaults.
- **Full ribbon library before the video (Saad, 22 Jul 2026):** after F11, run
  `make circuits` across all ingested events and commit the GLBs (~100 KB each,
  ~2.6 MB total) so the demo and a clean clone show the whole circuit library, not 3
  circuits. Recorded in docs/plans/F11-plan.md decisions.
- **AR-10 race fuel (spec Part 8):** VERIFIED 16 Jul 2026 — the FIA 2026 regs cap fuel
  energy flow at 3,000 MJ/h (energy-based, replacing 100 kg/h) and the race allowance
  works out to ~70 kg with the Advanced Sustainable Fuel spec. Sources: Formula1.com
  2026 regulation explainers; FIA 2026 Technical Regulations issue 8 (24 Jun 2024).
  The assumption stands as written ("about 70 kg, energy-flow limited"); next fits
  session may lift the grade-C flag per the register's close-out rule.

- **AR-04 energy store (spec Part 8):** VERIFIED 24 Jul 2026 — official FIA regulation
  text. FIA 2026 Formula 1 Technical Regulations Issue 8 (24 Jun 2024), Art 5.4.9: "The
  difference between the maximum and the minimum state of charge of the ES may not
  exceed 4MJ at any time the car is on the track" — unchanged in the consolidated 2026
  Section C Issue 18 (7 May 2026) as Art C5.2.9. The rule is continuous in substance
  since 2014, though the 2025 regs carry it in the Art 5.3.2 energy-flow diagram, not
  prose (the register's "Art 5.4" pointer resolves to 5.4.9 in the 2026 issue the spec
  cites). Precision for the viva: the regs regulate a max–min delta SoC, not "usable
  capacity" — total cell energy is unregulated and larger — so SOC in [0, 4] models the
  regulated window exactly. Bonus: the 2014–2025 "max 4MJ/lap from ES to MGUK" diagram
  label is absent from the 2026 text, which is primary-source confirmation of F-02.
  The configs/physics_2026.yaml usable_capacity_mj comment now cites Art 5.4.9 / C5.2.9
  (done in F12, 24 Jul 2026).
- **Harvest-cap refinement to re-check before F14 (found during AR-04, 24 Jul 2026):**
  the FIA's 20 Apr 2026 refinements cut maximum permitted recharge from 8 MJ to 7 MJ
  (Issue 18 Art C5.2.10; floor of 5 MJ in qualifying; +0.5 MJ Manual Override under
  B7.2). Every circuits.yaml h_max_mj is still the 8.5 default — exactly the E-02 case.
  Re-verify per-event values against C5.2.10 before F14's headline runs.

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
