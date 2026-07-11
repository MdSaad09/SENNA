# F15 — Demo, docs, reproducibility pack & freeze

Depends on: F10, F11, F12, F13, F14
Spec anchors: 5.13, 5.11 (repro pack), A-09, R-07, R-08, Part 6.3

## Goal
Ship it: the engineered first 90 seconds, a reproducibility pack an examiner can rerun,
and the final frozen deploy.

## Deliverables
- The demo deep link opening mid-race per the 5.13 storyboard: live view -> decision card with fidelity badge -> counterfactual split -> energy view; the long-form script updated per the four spec edits
- A README a hiring manager reads in three minutes: what, why, the honest limits, how to run it
- The reproducibility pack (A-09): seeds.yaml manifest, config hashes in every result row, a frozen data snapshot archived, and make ingest / fit / train / eval / report all real
- The "unofficial project, not associated with Formula 1" footer everywhere public (R-07)
- Final Railway deploy, a tagged release, and the demo video

## Out of scope
Anything new — this feature adds finish, not capability. Mobile 3D and broadcast cameras stay cut (R-08).

## Constants & configs
- Nothing new; the freeze IS the deliverable — tag the model version, data snapshot and config hashes together

## Tests first
- Cold-start: a fresh clone plus the make targets reproduces the headline-table hashes
- Demo link: a cold browser reaches mid-race within the 15-second beat
- A link-rot pass over README and INDEX

## Done means
- The demo works from a cold cache on someone else's machine
- make report reproduces Chapter 7 from the snapshot
- The repo is tagged, INDEX shows every feature Done, and nothing from the Part 6.3 never-cut list was cut

## Notes for the plan session
Check the timeline anchor before planning. If behind, apply the Part 6.3 cut order here
— to views and polish, never to the never-cut list.
