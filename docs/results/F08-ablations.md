# F08 — ablations and headline runs: the evidence base

The 5.6.3 ablation set, run as specified: four arms at a 4M-step ceiling and two
seeds each, every arm Stage C from scratch so the no-curriculum arm doubles as the
matched control, plus the 3-seed headline under the full curriculum. Selection used
validation seeds only; the held-out test seeds and test rival band stay untouched
for F14. The machine-readable twin of this document is `models/runs.json` (the run
ledger); curves live in the offline W&B runs named in the table (sync when an
account exists). All runs completed 19 Jul 2026 on the post-guard code
(`git_commit` in each manifest is the discriminator against the archived pre-guard
Stage A run).

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
visible in its training curves (`reward/violation_penalty_ep_mean`), not in its
selection score — the final-policy compliance gap is F14's measurement.

## Run table

| Run | Seed | Budget | Exit | Selected (val. points @ step) | Config hash | W&B id |
|---|---|---|---|---|---|---|
| ablation: no_curriculum | 101 | 4M | stagnation | 5.740 @ 2,260,992 | 3117b1579700 | yhad8q09 |
| ablation: no_curriculum | 211 | 4M | stagnation | 4.078 @ 2,064,384 | 3117b1579700 | 4r7xe2at |
| ablation: penalty_constraints | 101 | 4M | ceiling | 3.938 @ 3,932,160 | cdc1d13b6b2d | 1nczckex |
| ablation: penalty_constraints | 211 | 4M | ceiling | 4.917 @ 4,005,888 | cdc1d13b6b2d | xlhg1k6p |
| ablation: reward_v2 | 101 | 4M | ceiling | 3.815 @ 4,005,888 | 83a9dab3a3d5 | k3ywwjqj |
| ablation: reward_v2 | 211 | 4M | ceiling | 4.052 @ 3,932,160 | 83a9dab3a3d5 | v7u5jbnc |
| ablation: terminal_only | 101 | 4M | ceiling | 6.638 @ 4,005,888 | 3fb235e6450b | maqx1j79 |
| ablation: terminal_only | 211 | 4M | ceiling | 5.828 @ 4,005,888 | 3fb235e6450b | gcrdzmij |
| headline | 101 | 8M | stagnation | 6.415 @ 2,064,384 | 6b6edb78d84e | xdg1uu8n |
| headline | 211 | 8M | stagnation | 6.257 @ 1,179,648 | 6b6edb78d84e | hcnmr25t |
| headline | 331 | 8M | stagnation | **6.517 @ 835,584** | 6b6edb78d84e | 9x3vssoq |

Steps are global; a headline selection step includes the Stage A/B laps that came
before it. The reward_v2 seed-211 row carries `attempts: 3` in the ledger — two
interrupted starts, restarted from zero per the documented resume policy. Exit
"stagnation" is the Stage C stop (best validation points stale for 1M steps)
recorded as the gate; "ceiling" means the 4M budget arrived first.

## Readouts

### Ablation 1 — no curriculum (Stage C from scratch)

The curriculum earns its keep on both level and stability. Every headline seed
beats every control seed (6.26–6.52 vs 4.08–5.74), the headline's seed spread is a
quarter of the control's (0.26 vs 1.66 points), and the curriculum runs reach
their best checkpoints early enough that all three stagnation-stopped with most of
their Stage C budget unspent. The honest caveat is the protocol itself: both
control seeds stagnation-stopped near 2M steps, so the comparison is "each regime
allowed to stop when it stopped improving", not matched step counts — the W&B
curves carry the at-matched-steps read, and it does not change the ordering.

### Ablation 2 — penalty-based constraints instead of masks (F-16)

The direct F-16 test behaved exactly as the finding predicts. During learning the
violations are real: random play in the penalty world commits ~22.6 violations per
race (measured over 20 races — overwhelmingly empty-store attack requests, plus
the two-compound breach), and the `reward/violation_penalty_ep_mean` curves show
the arm spending its early budget buying that count down. The selected policies
end at 3.94/4.92 validation points — below the masked control's 4.91 mean and some
1.5 points under the terminal-only arm that differs from it only in constraint
architecture plus shaping. Replaying the better seed's selected policy over 20
races produced 0.00 violations per race, which is the point in miniature: the
penalty arm had to *learn* what masking provides by construction, and a measured
zero over 20 races is still not a guarantee — v2's own "99.5% compliant" framing
is why compliance moved out of the reward (the residual rate on the full eval
logs is F14's M10). Structural honesty note, pre-registered: the pit lane never
closes in live play and the unfitted-compound guard holds in every mode, so the
violations available to this arm are the wet-tyre rules, the two-compound rule
and the SOC-floor attack.

### Ablation 3 — v2's twelve-term reward

The likely publishable negative result arrived on schedule. Both seeds are the
worst on the board (3.815/4.052 — a consistent, tight, bad pair), both ran to the
full 4M ceiling without ever stagnating, and the dominance-ratio telemetry shows
why: the twelve terms bury the terminal objective under shaping income the agent
can farm without finishing higher, exactly the F-15/F-17 mechanism (the +0.2
oscillation pump and the pay-to-pit-early grip bonus are both reproduced verbatim
in `senna/env/reward_v2.py`). The reconstruction caveats stand as documented in
`configs/ablations.yaml` — the fuel-penalty magnitude, undercut labelling rule
and ERS-violation trigger are flagged `reconstructed`, and in v2 mode the
position decomposition is the gain/loss pair, not a zeroed v3 `position` key —
but the qualitative conclusion does not hinge on them: heavy shaping hurt, by
roughly a point against the matched control and 2.4 points against the headline.

### Ablation 4 — terminal-only reward

The most interesting number in the study. With both shaping terms off, the sparse
terminal signal alone reached 6.638/5.828 — beating the matched control (same
regime, shaping on) by about 1.3 points on the mean and landing within noise of
the full-curriculum headline. At this budget, with masks doing the compliance
work and the horizon a single race, v3's light shaping is not load-bearing and
may even be slightly costly in the from-scratch regime; the shaping terms'
defensible role is narrowed to per-lap credit legibility (the decomposition the
interpretability contract wants) rather than raw performance. Two seeds are not a
theorem — the dissertation should present this alongside the gamma-sensitivity
one-liners and the dominance ratio rather than as a settled claim — but it is a
finding worth a section, not a footnote.

### Headline — 3 seeds, full curriculum

All three seeds cleared their Stage A and B gates and stagnation-stopped in
Stage C with tightly grouped validation scores (6.257 / 6.415 / 6.517). Selection
followed the 5.7 rule extended across seeds — highest validation points, ties to
the earlier step, then the lower seed — and chose **seed 331 at global step
835,584: `senna-ppo-6b6edb78d84e-C-00835584`**, promoted to `models/headline/`
with the triplet verified against the gate log before copying. This is the model
version F09 explains and F10 serves. Test seeds, the test rival band and every
M1–M11 number remain untouched for F14.
