# F15 — Demo, docs, reproducibility pack & freeze — plan

F15 adds finish, not capability: the engineered first 90 seconds made executable in
a real browser, a README a hiring manager reads in three minutes, the A-09
reproducibility pack completed, the three cuts inherited from F14 closed, and the
freeze — tag, snapshot, verify. Planning exploration changed the shape of the
work: most of the repro pack already exists (all 18 Makefile targets are real,
`configs/seeds.yaml` is frozen and consumer-gated, every store JSON carries a
provenance envelope, `make report` is a pure byte-deterministic function of the
committed store), while several things the 5.13 storyboard depends on do not (no
way to open the live view mid-race, no SOC bar, no fidelity badge element, nav
links drop the query string). Timeline is not a factor — planning happens 28 Jul
against a 17 Nov anchor — so the Part 6.3 cut order is never invoked.

## Objective & spec anchors

- **5.13** — the four-beat storyboard (deep link mid-race → decision card with
  fidelity badge → counterfactual split → energy view) and the four edits that
  turn the v2 long-form script into the tour. The 15-second first beat becomes a
  measurable budget in a Playwright check.
- **5.11 / A-09** — the pack is `make ingest / fit / train / eval / report`, a
  seeds.yaml manifest, config hashes in result rows, a frozen data snapshot.
  What is genuinely missing: the snapshot (no mechanism exists at all), the
  README, `make eval` meaning what the spec's enumeration means (today it is a
  per-run checkpoint rescore; the M1–M11 battery is `make suite`), and
  consistent hash attribution in the report.
- **R-07 / F-29** — the unofficial-project footer already ships on every route
  (`frontend/src/App.tsx:62-65`, tested) but with wording that differs from the
  spec's. Master spec wins: one canonical string, applied everywhere public.
- **R-08** — mobile 3D and broadcast cameras stay cut. Nothing here touches them.
- **Part 6.3** — the never-cut list (action masking, cleaning contract,
  calibration/validation split, metric suite with gaming notes, decision cards)
  is verified intact and recorded in the release notes. Part 6.3 lives only in
  the PDF, so a faithful extraction lands as `docs/spec/6.3-cut-order.md`.

Two conflicts, both resolved by Saad (see Decisions):

1. The feature spec says "Final Railway deploy"; the decisions log (22 Jul)
   defers Railway in favour of `docker compose up --build` plus the video. The
   deferral stands.
2. 5.13 says the v2 ten-minute script "is kept with four edits", but Section
   14.2 is a dangling forward reference — the v3 PDF has no such body and no v2
   document is in the repo. The long-form script is authored fresh, honouring
   the four edits (ERS Landscape beats become Energy view beats; "Verstappen's
   car" becomes the three-letter data code; the W&B beat adds the
   masking-vs-penalty ablation; the closing GitHub beat shows the
   reproducibility Makefile).

## Findings from planning (all verified in code)

1. **The serving flip is one artifact and one flag away.** The F14 registry
   landed: `senna/serve/loader.py:74-99` walks `serving.yaml baked_models` and
   raises `UnknownModelVersionError` only because
   `models/explain/senna-ppo-db031aead155-C-02211840/` does not exist; that
   raise is the whole `pending-F14` caveat. But `senna/explain/run.py:49`
   hard-pins `_ERA = "2026"` — running it against the 2024 triplet today would
   distill the 2024 model on 2026 physics. The Stage C bank also includes
   `canadian_grand_prix`, which has no native 2024 fits
   (`senna/eval/traces.py::require_native_era_fits` exists to refuse exactly
   this). `.gitignore:23` negates only the headline surrogate dir, and
   `Dockerfile.api:24-26` + `.dockerignore` bake only headline + explain — the
   committed `models/era2024/` is invisible to the image the demo runs.
2. **Clearing the caveat changes no dissertation number.** The committed
   `m2_races.json` envelope already names the era2024 model — the offline M2
   ran era-matched. The flip only makes the served demo honest.
3. **The extract writer is exactly as F14 left it.** `strategy/extract.py`
   prints the race winner's plan; its docstring has claimed it writes
   `configs/real_strategies.yaml` since F06. The yaml holds one of ten M2
   races, and its circuit-only key cannot hold the ten — they include two
   `british_grand_prix` entries (2024 HAM, 2023 NOR).
4. **The M2 coefficient sensitivity has a config key and no reader.**
   `configs/eval.yaml` `sensitivity.energy_coefficients.perturbation: 0.5`
   says "DEFERRED TO F15, no reader yet" in its own comment. The harvest-cap
   machinery (`overlay_configs`, both-arms-overlay discipline, paired-arm
   guard, subset-never-writes-to-root) is all reusable. The provenance half is
   also owed: the `# borrowed:` block in `configs/physics_2024.yaml` and the
   `scenario.py` note update that F14's plan promised.
5. **The live deep link exists and is tested; the mid-race part does not.**
   `?circuit`/`?seed`/`?run` work end-to-end
   (`LiveSimulationView.test.tsx:125-146`), but the WS always starts at frame
   0 at 1× (`api/ws.py:96,130`) and a cold link blocks until the whole
   simulation completes (`ws.py:53-73`). `client:seek` already exists — the
   frontend sends it on reconnect — so mid-race entry is a frontend change,
   not a protocol change.
6. **Storyboard gaps in the views.** No SOC bar on `/live` though
   `LapFrame.agent.soc_mj` is served; fidelity renders as monospace text in
   the honesty footer, not a badge; NavLinks drop the query string, so "one
   click to the Counterfactual view" is impossible; `EnergyLap.mode` is served
   and never rendered, so the "banked energy before an attack" hover shows
   only an SOC number.
7. **The Chrome canvas mystery has a benign prime suspect.** At 1× only lap 1
   exists for ~90 s — all 22 cars stacked at s≈0, viewed from 1.27 km. A
   deep-linked circuit with no ribbon produces the same near-empty symptom
   with no message. The seek work probably fixes it; the Playwright check
   proves it either way.
8. **No README, no tags, no release process.** The de-facto entry document is
   INDEX.md, which is an internal ledger. `git tag -l` is empty.
9. **Compose really does give a marker the full stack from a clean clone** —
   the serving artifacts are committed and baked, not mounted. Two lies to
   fix: `docs/deploy.md` claims "nothing is ever mounted" (false for the
   frontend dev-server bind mount) and never states the frontend URL; the
   compose worker healthcheck probes an HTTP port the RQ worker never opens —
   unhealthy on every machine since F10, unnoticed because nothing gates on it.
10. **Provenance loose ends.** `models/runs.json` is gitignored despite being
    cited as "the machine-readable twin" of the ablation table;
    `eval/sensitivity.py` fingerprints one config file where the suite
    fingerprints eleven, and the report prints the suite's hash above the
    sensitivity section — an examiner would mis-attribute it; the committed
    `F14-evaluation.md` differs from what `report.py` emits today (a stale
    mid-word break), with an uncommitted regeneration sitting in the working
    tree.

## Decisions (Saad, 28 Jul 2026)

1. **Railway stays deferred** per the 22 Jul decision. The release notes say
   the runbook exists but is unverified in production. Revisit only if a live
   URL is wanted before the viva.
2. **The canonical disclaimer is the F-29 wording**, mirroring OpenF1's own:
   "SENNA is an unofficial project and is not associated in any way with the
   Formula 1 companies, the FIA or any team." It replaces the current footer
   text and appears in the README and the video end card.
3. **Snapshot = pg_dump + committed manifest + GitHub release asset.** The
   dump is gitignored, its sha256 and row counts are committed, and the file
   rides the `v1.0.0` release. **Open item:** if the COMP702 submission is a
   self-contained bundle rather than repo access, the snapshot must travel
   with the bundle or via university storage — Saad confirms the submission
   mechanism before the freeze. The 12 GB FastF1 cache stays local either
   way, with that limit stated in the README.
4. **Ship-gate process:** `rm -rf .ruff_cache` before the final lint (the
   warm-cache I001 lesson), `make verify` is part of the ship gate, and CI is
   checked green after `/land`.

## Deliverables

### A. Close the three F14 inheritances

1. **Serving flip.** `--era` on `senna/explain/run.py` (era selects physics for
   distillation and card envs), circuit narrowing through
   `require_native_era_fits`, `TRIPLET=`/`ERA=` passthrough on `make explain`,
   `.gitignore` negation for the new surrogate dir. Then the real run:
   `make explain TRIPLET=models/era2024 ERA=2024`, surrogate committed. Tests
   un-pin the `pending-F14` literal (they read the expected string from the
   era2024 manifest), the never-written graceful-degrade test
   `test_counterfactual_route_degrades_to_pending_when_unbaked` lands,
   `/agents` lists both models, frontend fixtures update. `Dockerfile.api` and
   `.dockerignore` bake `models/era2024/` and its surrogate so the compose
   demo can actually serve the flip.
2. **Extract writer.** `--driver <abbrev>` and `--write` on
   `senna/strategy/extract.py`, params_writer-style merge. The store re-keys
   to season+driver (the two British GP entries force it);
   `load_real_plan` and its two test callers update; the nine missing entries
   are written with per-entry provenance; the docstring stops lying. M2's
   harness keeps its Postgres path — its numbers are frozen — and the yaml is
   the committed, human-readable record.
3. **M2 energy-coefficient sensitivity.** `senna/eval/coefficients.py`, a
   sibling of the harvest machinery reusing `overlay_configs` and the
   paired-arm guard: the four borrowed 2026 coefficients at ±50%, the ten
   races re-rolled paired, results in
   `docs/results/F14/store/m2_sensitivity.json` with its own envelope. A
   separate file, not rows injected into `m2_races.json` — mixing two runs'
   envelopes in one file corrupts provenance; this diverges from F14-plan's
   wording deliberately. Report section and Makefile entry. The `# borrowed:`
   block lands in `configs/physics_2024.yaml` and the `scenario.py` note
   updates to "sensitivity-checked".

### B. Make the storyboard executable

4. **Mid-race deep link.** `?lap=` and `?speed=` handled client-side, reusing
   the existing `client:seek` on connect. These params never enter the POST
   body — the E-15 cache key is the byte-identical request body, and forking
   it would orphan pre-warmed demo runs.
5. **SOC bar on `/live`.** Renders the served `soc_mj` per frame. The 0–4 MJ
   scale comes from the API (no client-side physics); if no served field
   carries it, that is a 5.9.2 shape addition flagged as a spec divergence,
   not smuggled in.
6. **Fidelity badge.** The served agreement figures move from monospace footer
   text to a visually distinct badge on the decision card. Same data, no new
   numbers.
7. **One-click view flow.** NavLinks preserve `location.search`; the canonical
   demo URL carries the union of params
   (`circuit, seed, run, lap, speed, year, round, driver`) and every view
   reads what it needs, ignoring the rest. No new endpoints, no demo mode.
8. **Energy-beat hover.** The served `mode` joins the SOC tooltip. The
   harvest-cap line stays on the bars panel where it is physically meaningful
   — an 8.5 MJ/lap cap drawn on a 0–4 MJ SOC axis would be a physics-display
   error. The script narrates the two panels; this is a deliberate reading of
   5.13's compressed sentence.
9. **Demo warm + browser check.** `scripts/warm_demo.sh` POSTs the demo
   simulations against the local stack (a cold link blocks until the sim
   completes, so the 15-second beat only works pre-warmed — E-15-legal, and
   honest because the run is real). A minimal Playwright smoke
   (`make demo-check`, local only, never CI) drives a cold Chrome to the demo
   URL and asserts cars on track within the beat budget. This is also the
   harness that closes the INDEX open item on the near-empty Chrome canvas.
   Demo-circuit pick at ship time: committed ribbon, native fits, ASCII slug
   (`são_paulo_grand_prix` is a URL-encoding hazard), a pit call near lap 18
   with a clean SHAP story.
10. **`docs/demo/script.md`.** The 90-second beat sheet with exact URLs and
    clicks, the ten-minute long-form script authored fresh with the four edits
    applied, and the recording checklist (real Chrome; the quality toggle —
    bloom defaults off on Intel renderer strings, so a recording laptop needs
    it clicked; E-18 overlay behaviour; the end-card disclaimer).

### C. README and repro pack

11. **`README.md`.** Three minutes: what and why; the honest limits — M1 +2.08
    and M10 clean read against M9's 37.3 tyre failures per 100 races, M2 an
    honest wash at n=10 under a pre-registered sign test, M4's
    unattainable-by-construction ceiling, M5's VSC recall 0.000 with the
    mechanism labelled a hypothesis (exactly as the F14 lesson insists), M8's
    miss caused upstream in F03's transform with E-14 forbidding a refit,
    M11's 0.758 luck share as the novel finding; how to run it
    (`docker compose up --build`, the demo URL, `make report`); the
    disclaimer; the AI-assistance declaration pointer (COMP702 / OQ-3).
12. **Frozen data snapshot.** `make snapshot`: `pg_dump -Fc` to
    `data/snapshot/` (gitignored) plus a committed
    `data/snapshot/MANIFEST.md` — sha256, size, per-table row counts, pg_dump
    version, date. `make restore` targets `senna_test` by default and routes
    through `require_disposable`; restoring the real DB requires the named
    escape hatch. The dump is attached to the GitHub release via curl (no gh
    installed).
13. **Makefile truth pass.** The stale "each stub becomes real" header becomes
    an entry-point map; the current `eval` renames to `rescore` and `eval`
    runs the M1–M11 suite so the A-09 enumeration means what it says (every
    `make eval` reference greped and updated); new targets: `test` (mirrors
    CI's `pytest -m "not slow"`), `snapshot`, `restore`, `verify`,
    `demo-warm`, `demo-check`.
14. **Config-hash consistency.** The report renders each section's own
    envelope hash; `sensitivity.py` widens its fingerprint list for future
    runs (the committed row keeps its recorded hash — no re-roll of the
    harvest study); `models/runs.json` is committed.
15. **`make verify` + CI.** Three checks, all cheap and pure: regenerate the
    report from the committed store and diff byte-for-byte against the
    committed doc; recompute config fingerprints from the yaml files on disk
    and compare against the committed store envelopes (proving the configs in
    the tag are the configs the results came from); run the link checker.
    Added as a CI job. Sequencing matters: report.py changes land first, the
    doc regenerates once, then the byte-check pins it.
16. **`scripts/check_links.py`.** The link-rot pass, wired into `make verify`.
    Today's surface is small (INDEX's 15 lesson links all resolve); the risk
    is the new README.
17. **Deploy truth pass.** `docs/deploy.md` fixes the mount claim and states
    the frontend URL; the compose worker healthcheck becomes an rq/redis
    probe (or is dropped) with an operational-origin comment.

### D. The freeze

18. **Tag and release** (after `/land F15` merges): INDEX final pass (every
    feature Done), annotated tag `v1.0.0` pinning the triplet versions
    (`senna-ppo-6b6edb78d84e-C-00835584`,
    `senna-ppo-db031aead155-C-02211840`), config fingerprints, seed-manifest
    hash and snapshot sha256 together; GitHub release with the snapshot
    asset; CI verified green after land, with `rm -rf .ruff_cache` before the
    final lint. The runbook lives in `docs/freeze.md`. The never-cut list is
    verified intact and recorded in the release notes.
19. **`docs/spec/6.3-cut-order.md`** — faithful extraction so the never-cut
    check no longer requires opening the PDF.

## Constants & configs

The feature spec says "nothing new; the freeze IS the deliverable", and no
physics or model constant appears. What F15 does introduce:

| Name | Value | Origin | Lives in |
|---|---|---|---|
| Demo beat budget | 15 000 ms | sourced — 5.13's 0–15 s beat | Playwright spec constant, comment citing 5.13 |
| Demo URL params (lap ≈ 18, speed, circuit, seed) | picked at ship | stylised — 5.13 storyboard | `docs/demo/script.md` + README; URL data, not code constants |
| SOC bar scale | served by the API | — | no client constant; 5.9.2 divergence flagged if a field must be added |
| Snapshot paths / dump format | `data/snapshot/`, `pg_dump -Fc` | operational | Makefile comments with sizing rationale |
| Worker healthcheck probe | rq/redis-based | operational | docker-compose.yml comment |
| M2 coefficient perturbation | 0.5 | already in `configs/eval.yaml` (F14); F15 adds the reader | — |

## Tests first

Written and shown failing before implementation:

- `test_extract_writes_a_driver_entry` — `--driver`/`--write` round-trips
  through `load_real_plan` (the test F14's plan specced and never wrote).
- `test_real_strategies_covers_all_m2_races` — all ten eval races under the
  season+driver key, both British GP entries included.
- `test_explain_era_threading` — era 2024 selects 2024 physics for
  distillation and card envs.
- `test_explain_narrows_to_native_era_fits` — the 2024 run excludes
  `canadian_grand_prix`.
- `test_counterfactual_route_degrades_to_pending_when_unbaked` — plus
  un-pinning the two tests that assert the literal.
- `test_agents_route_lists_both_models`.
- `test_coefficient_sensitivity_writes_paired_arms` — both arms overlaid,
  paired-arm guard honoured, separate store file with its own envelope.
- `test_report_attributes_each_sections_own_hash`.
- `test_report_reproduces_committed_doc` — byte-for-byte; also the CI job.
- `test_fingerprints_match_committed_envelopes` — the freeze guard.
- `test_snapshot_roundtrip` (slow-marked, local) — dump → restore into
  `senna_test` through `require_disposable` → manifest row counts match.
- `test_check_links_finds_a_broken_link` — the checker catches a planted case.
- Frontend (vitest): `?lap=`/`?speed=` triggers seek and speed without
  touching the POST body; the SOC bar renders from frame data; the fidelity
  badge is present with the served agreement figure; NavLinks preserve the
  query string; the SOC tooltip shows the served mode.
- Playwright `demo.spec.ts` — a cold browser reaches mid-race (cars on track,
  non-empty canvas) inside the beat budget; `make demo-check`, never CI.

Property tests: none new. F15 adds no physics, env or reward behaviour — the
existing property suite is the thing being frozen. The closest analogues are
the byte-determinism and fingerprint-consistency checks above.

## Edge cases handled

- **E-15** — deep-link params stay out of the POST body so pre-warmed cache
  keys survive; the era-2024 explain run persists cards under the 2024 model
  version; README and runbook state that any retrain invalidates cards,
  surrogate and warm runs by construction.
- **E-16** — mid-race entry is a seek over stored frames on the playback
  clock: reads, never re-simulation. The blocking-until-complete behaviour on
  cold links is why the warm step exists.
- **E-18** — context-loss overlay already handled; the recording checklist
  verifies it and the bloom/quality toggle on the recording machine.
- **E-14** — the README's M8 paragraph states the cause is the F03 transform
  and that refitting on held-out rounds is forbidden; no fix is attempted.
- **E-02** — the energy beat and README tell the measured harvest-cap story
  (8.5 kept; at the FIA's refined 7.0 the frozen agent loses 0.13 places and
  its derate share goes 0.078 → 0.182) rather than a hard-coded cap claim.
- **E-12** — snapshot/restore are local-only; CI's new job is the pure report
  check, no bulk data work.

## Acceptance checklist

- [ ] The demo works from a cold cache on someone else's machine — fresh
      clone → `docker compose up --build` → warm script → the demo URL passes
      `make demo-check` in real Chrome, and the runbook says exactly this
- [ ] `make report` reproduces Chapter 7 from the committed store,
      byte-for-byte, checked in CI
- [ ] A fresh clone's `make verify` passes: report bytes,
      fingerprint-vs-envelope match, no rotten links
- [ ] The `pending-F14` caveat is gone from the served counterfactual view;
      `/agents` lists both models; the 2024 surrogate is committed and baked
- [ ] `real_strategies.yaml` holds all ten M2 races; the extract docstring no
      longer lies
- [ ] The M2 ±50% coefficient sensitivity exists in store and report; the
      borrow is documented in physics_2024.yaml
- [ ] README exists, reads in three minutes, carries the honest-limits section
- [ ] The canonical F-29 disclaimer is in the app footer, README and video
      end card
- [ ] Snapshot dump + committed manifest exist; the restore round-trip test is
      green against `senna_test`
- [ ] INDEX shows every feature Done; tag `v1.0.0` pins model versions, config
      hashes and snapshot sha256; the release carries the dump; CI green after
      land with a cold-cache lint (`rm -rf .ruff_cache` first)
- [ ] Nothing from the Part 6.3 never-cut list was cut — verified and recorded
      in the release notes
- [ ] The live-view Chrome canvas item is closed with evidence (Playwright
      pass plus the seek fix or the real diagnosis)

## Out of scope

- Anything new in capability: no new views, no demo mode, no new endpoints
  beyond a possible single 5.9.2-flagged field for the SOC scale.
- Mobile 3D and broadcast cameras (R-08).
- The Railway production deploy (Decisions, 1).
- Re-running the harvest-cap sensitivity or any training/eval battery to
  refresh hashes — frozen numbers stay frozen.
- Fixing M8's transform, M5's VSC behaviour or any other metric miss — that is
  dissertation discussion material, not F15 code.
- A yaml-only M2 harness (M2 keeps its Postgres dependency; the README states
  the limit).
- Recording the video itself — Saad, with the script, checklist and warmed
  stack F15 delivers.
