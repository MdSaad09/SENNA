# Part 8 — Assumptions register (2026 physics and data)

Extracted from the SENNA Master Implementation Specification v3.0 (7 July 2026) — docs/spec/source/SENNA_Master_Spec_v3.pdf, Part 8. The PDF is the authority; report divergences, never patch them here.

Every load-bearing assumption, graded: A = verified against two or more primary sources this week; B = single good source; C = must be fitted from data or verified before the phase that uses it. If a row changes, the config file changes — never the code.

| ID | Assumption | Grade | Source | If wrong -> action |
|---|---|---|---|---|
| AR-01 | MGU-K max 350 kW (v2's 400 kW was the ICE) | A | Formula1.com 2026 PU explainers; FIA 2026 PU regs | Update constants yaml; refit T1 |
| AR-02 | Deployment taper: full to 290 km/h, zero at 355 km/h | A | Formula1.com explainer | Refit E_dep integrals |
| AR-03 | Manual Override: 350 kW to 337 km/h, ~0.5 MJ, within 1.0 s | A | Formula1.com; ESPN 2026 guide | Adjust override feature + T7 |
| AR-04 | Energy Store usable capacity 4 MJ (unchanged) | A | ESPN 2026 guide; cross-check FIA Art. 5.4 | Change SOC bound everywhere via config |
| AR-05 | Harvest cap 8.5 MJ/lap baseline; FIA-adjusted ~5-9 per event; extra quali reductions. REFINED 20 Apr 2026: Issue 18 Art C5.2.10 cuts maximum recharge to 7 MJ (5 MJ quali floor, +0.5 MJ under Manual Override, Art B7.2) — verified 26 Jul 2026. circuits.yaml stays at 8.5 because the frozen headline trained there and its manifest records that fingerprint; the 7 MJ figure is measured as an eval-only overlay (configs/eval.yaml sensitivity.harvest_cap, reported in docs/results/F14-evaluation.md: 0.13 places and +0.104 derate share). | A | FIA regs; Raceteq (May 2026); Autosport (Mar 2026); FIA 2026 Technical Regulations Issue 18 Art C5.2.10 | Per-event H_max values in circuits.yaml; correcting the baseline means re-running synth -> train -> promote -> explain, not editing one value |
| AR-06 | Lift-and-coast harvests at 350 kW and forces Z-mode (drag cost) | B | Raceteq 2026 energy explainer | Adjust conserve-mode cost c_lc |
| AR-07 | Super clipping recovers at ~250 kW on throttle | B | Autosport Mar 2026 | Adjust H_clip term |
| AR-08 | Aero vs 2024: downforce about -30%, drag about -55% | B | Honda 2026 regulations overview | Refit T2 |
| AR-09 | Minimum mass 768 kg (-30 kg) | A | Honda overview; F1 aero explainer | Refit T3 |
| AR-10 | Race fuel mass about 70 kg, energy-flow limited | C — VERIFY before Phase 2 | To confirm vs FIA 2026 regs | Set from the verified figure in T6 |
| AR-11 | Fastest-lap championship point abolished from 2025 | B — 30-second check | 2025/2026 Sporting Regulations | If somehow restored: add back as an eval metric, not a reward |
| AR-12 | 22-car grid (11 teams, Cadillac entered) | A | 2026 season fact | Grid size is a config value |
| AR-13 | 2026 calendar currently 22 rounds; Madrid new in September; roughly 10 rounds raced by 7 July | A | Sky Sports / season reporting | Circuit library is data-driven (F-08) |
| AR-14 | Ergast dead since early 2025; FastF1 >= 3.7 serves the same interface from Jolpica | A | FastF1 3.7 documentation; project announcements | None — v3 already assumes it |
| AR-15 | OpenF1: 2023 onward, free historical at ~3 req/s, real-time paid | A | openf1.org | Throttle values in ingest config |
| AR-16 | FastF1 car/pos telemetry cadence roughly 4-5 Hz (not 10 Hz) | B | FastF1 documentation | Energy integrals are cadence-aware already |
| AR-17 | 2026 dirty-air penalty smaller than 2024 (closer-racing intent) | C — fit | Design assumption | Fit traffic term from 2026 rounds in T7 calibration |
| AR-18 | 2026 Pirelli compound behaviour differs from C1-C5 | C — fit | Pirelli 2026 announcements | T5 refits from rounds 1-6 by design |

## Primary sources consulted for this revision (7 July 2026)

- Formula1.com — "2026 regulations explained: power units" (Jan 2026) and the 2026 PU / aerodynamics explainers (2024); F1 2026 terminology update (Dec 2025).
- FIA — 2026 Formula 1 Power Unit Technical Regulations (Art. 5: ERS-K power, per-lap harvest limits, ES).
- Raceteq — "MGU-K, megajoules and managing the battery: F1's 2026 energy system explained" (May 2026).
- Autosport — "FIA cuts recoverable energy in F1 qualifying" (Mar 2026).
- ESPN — "2026 F1 rules: what's new on the cars" (Mar 2026).
- Honda Global — 2026 Formula 1 Regulations Overview (Jan 2026).
- FastF1 3.7 documentation — Jolpica-F1 API interface; Fast-F1 GitHub discussion #445 (Ergast deprecation).
- openf1.org — API documentation and access-tier notes.
- Sky Sports F1 / season reporting — 2026 calendar status, Cadillac entry, 22-car grid.

## Approval checklist — what happens next

1. Read Part 0, then Parts 1, 3 and 4 (the audit and the change lists). Part 5 can wait until the build.
2. Answer the twelve questions in Part 7 (one message; "use defaults" is a valid answer for most).
3. Show your supervisor Part 1 findings F-01 to F-09 and the Part 3 cut list — five minutes, and it protects you.
4. Reply "approved" (with any edits). We then start Phase 0 the same day, using Part 6.1 as the working method.

End of specification. Version 3.0 — prepared 7 July 2026 — supersedes v2.0 in full. Where v2 was right, it is carried forward by name; where it was wrong, the correction and its source are recorded above.
