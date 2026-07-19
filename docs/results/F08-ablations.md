# F08 — ablations and headline runs: the evidence base

The 5.6.3 ablation set, run as specified: four arms at a 4M-step ceiling and two
seeds each, every arm Stage C from scratch so the no-curriculum arm doubles as the
matched control, plus the 3-seed headline under the full curriculum. Selection used
validation seeds only; the held-out test seeds and test rival band stay untouched
for F14. The machine-readable twin of this document is `models/runs.json` (the run
ledger); curves live in the W&B runs named in the table.

**Why there is no DQN arm.** v2 planned a DQN baseline. It cannot run here, and the
reason is architectural, not budgetary: the action space is MultiDiscrete([6, 4]) —
pit decision and energy mode are independent axes (F-18) — and SB3's DQN requires a
flat Discrete space. Flattening the space back to 12 entangled actions to
accommodate DQN would undo the fix F-18 exists to make. The ablation grid was cut
from v2's compute-impossible 8 × 20M to these four 4M arms for the same audit
reasons (F-22, R-06).

A note on what selection measures: every arm, penalty included, is selected by mean
validation points scored in the default masked, v3-reward environment, so the
numbers are comparable across arms. The penalty arm's violations are therefore
visible in its training curves, not in its selection score — the final-policy
compliance gap is F14's measurement.

## Run table

<!-- filled from models/runs.json when the slate completes -->

## Readouts

### Ablation 1 — no curriculum (Stage C from scratch)

<!-- one paragraph after the runs -->

### Ablation 2 — penalty-based constraints instead of masks (F-16)

Pre-registered expectation: early training should show real violation counts —
exploration trips the SOC-floor and two-compound rules constantly. If steady-state
counts fall toward zero, that is itself the F-16 result: capacity spent learning
"don't press the illegal button" that the masked architecture never has to spend.
Note the structural ceiling on what this arm can violate: the pit lane never closes
in live play, and the unfitted-compound guard holds in every mode, so the
observable breaches are the wet-tyre rules, the two-compound rule and the
SOC-floor attack.

<!-- one paragraph after the runs -->

### Ablation 3 — v2's twelve-term reward

Reconstructed from the master spec's "v2 says" quotes; the fuel-penalty magnitude,
the undercut labelling rule and the ERS-violation trigger are flagged
`reconstructed` in configs/ablations.yaml, and the qualitative question — does
heavy shaping hurt? — does not hinge on them. The v2 magnitudes are 10–100x the
v3 reward's and reward normalisation stays off (correct for v3's hand-scaled
terms), so value-function instability is an expected part of this finding, not a
surprise to attribute after the fact. In v2 mode the position decomposition is the
gain/loss pair, not a zeroed v3 `position` key — the split is v2's own shape.

<!-- one paragraph after the runs -->

### Ablation 4 — terminal-only reward

<!-- one paragraph after the runs -->

### Headline — 3 seeds, full curriculum

<!-- selection evidence and the promoted model version after the runs -->
