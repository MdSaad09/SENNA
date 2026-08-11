# F08 — ablations and headline runs: the evidence base

The 5.6.3 ablation set, run as specified: four arms at a 4M-step ceiling and two
seeds each, every arm Stage C from scratch so the no-curriculum arm doubles as the
matched control, plus the 3-seed headline under the full curriculum. Selection used
validation seeds only; the held-out test seeds and test rival band stay untouched
for F14. The machine-readable twin of this document is `models/runs.json` (the run
ledger); curves live in the offline W&B runs named in the table (sync when an
account exists).

Every run below was re-trained on 11 Aug 2026, when F18 refitted the physics on the
full 2022–2025 era. The first grid ran on 19 Jul 2026 against constants fitted on
two seasons of the four available, so it is superseded rather than merely older. Its
numbers are kept beside the new ones throughout, because "the physics improved and
here is what moved" is a better answer than a clean slate. The `git_commit` in each
manifest still discriminates against the archived pre-guard Stage A run.

**What moved, in one line.** Three of the four arms land within about a point of
where they were, the headline is unchanged for practical purposes (6.397 mean against
6.396), and one comparison inverted: the penalty arm now outscores the matched
control. That inversion is treated below as evidence about the two-seed protocol
rather than as a new result about penalties.

**An unplanned reproducibility check, worth more than it cost.** The grid was
trained twice on the refitted physics. Between the two slates `configs/fits.yaml`
gained the two write gates F18 declares, which moved the training fingerprint and so
forced a re-run, but which no part of the environment reads. Every one of the eleven
runs came back identical to its predecessor — not close, identical, to the last digit
of a float: 6.3549999999999995, 4.418333333333334, 6.0233333333333325, and the rest.
Seed 331 won both times at the same step. The era-matched fine-tune reproduced too.

That is the strongest statement this project can make about determinism, and it was
not designed: same seed and same behaviour-bearing config give the same checkpoint,
across a config edit that changed the recorded preimage and nothing else. It also
prices the gate honestly — the retrain cost about two hours and bought no new number,
only a fingerprint that reproduces from the configs the repo ships.

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

The grid as it stands, on the full-era physics (11 Aug 2026):

| Run | Seed | Budget | Exit | Selected (val. points @ step) | Config hash | W&B id |
|---|---|---|---|---|---|---|
| ablation: no_curriculum | 101 | 4M | stagnation | 4.315 @ 1,179,648 | cab315f92c5b | 4dkwngu0 |
| ablation: no_curriculum | 211 | 4M | stagnation | 4.418 @ 1,081,344 | cab315f92c5b | 5fkjq954 |
| ablation: penalty_constraints | 101 | 4M | stagnation | 4.522 @ 2,850,816 | dd6bc69ce817 | 3u8v8ecv |
| ablation: penalty_constraints | 211 | 4M | ceiling | 6.023 @ 3,833,856 | dd6bc69ce817 | r8np5lwv |
| ablation: reward_v2 | 101 | 4M | ceiling | 3.548 @ 4,005,888 | f4143d96fb51 | k9jv4h14 |
| ablation: reward_v2 | 211 | 4M | ceiling | 4.872 @ 3,833,856 | f4143d96fb51 | 2jeq38lm |
| ablation: terminal_only | 101 | 4M | stagnation | 6.457 @ 2,260,992 | f054bb667b1b | ta84576u |
| ablation: terminal_only | 211 | 4M | ceiling | 5.423 @ 4,005,888 | f054bb667b1b | 5620z1nn |
| headline | 101 | 8M | stagnation | 6.355 @ 1,130,496 | 70098e9d3425 | k4zvqmok |
| headline | 211 | 8M | ceiling | 6.295 @ 4,227,072 | 70098e9d3425 | hjvll2eu |
| headline | 331 | 8M | stagnation | **6.542 @ 1,769,472** | 70098e9d3425 | xmu03404 |

The superseded 19 Jul grid, on the two-season physics, for comparison:

| Run | Seed | Exit | Selected (val. points @ step) | Config hash | W&B id |
|---|---|---|---|---|---|
| ablation: no_curriculum | 101 | stagnation | 5.740 @ 2,260,992 | 3117b1579700 | yhad8q09 |
| ablation: no_curriculum | 211 | stagnation | 4.078 @ 2,064,384 | 3117b1579700 | 4r7xe2at |
| ablation: penalty_constraints | 101 | ceiling | 3.938 @ 3,932,160 | cdc1d13b6b2d | 1nczckex |
| ablation: penalty_constraints | 211 | ceiling | 4.917 @ 4,005,888 | cdc1d13b6b2d | xlhg1k6p |
| ablation: reward_v2 | 101 | ceiling | 3.815 @ 4,005,888 | 83a9dab3a3d5 | k3ywwjqj |
| ablation: reward_v2 | 211 | ceiling | 4.052 @ 3,932,160 | 83a9dab3a3d5 | v7u5jbnc |
| ablation: terminal_only | 101 | ceiling | 6.638 @ 4,005,888 | 3fb235e6450b | maqx1j79 |
| ablation: terminal_only | 211 | ceiling | 5.828 @ 4,005,888 | 3fb235e6450b | gcrdzmij |
| headline | 101 | stagnation | 6.415 @ 2,064,384 | 6b6edb78d84e | xdg1uu8n |
| headline | 211 | stagnation | 6.257 @ 1,179,648 | 6b6edb78d84e | hcnmr25t |
| headline | 331 | stagnation | 6.517 @ 835,584 | 6b6edb78d84e | 9x3vssoq |

Arm means, new against old: terminal_only 5.940 (6.233), penalty_constraints 5.272
(4.428), no_curriculum 4.367 (4.909), reward_v2 4.210 (3.933), headline 6.397 (6.396).

Steps are global; a headline selection step includes the Stage A/B laps that came
before it. Exit "stagnation" is the Stage C stop (best validation points stale for
1M steps) recorded as the gate; "ceiling" means the 4M budget arrived first. The
`attempts: 3` on the old reward_v2 seed-211 row was two interrupted starts restarted
from zero; every run in the new grid completed first time.

## Readouts

### Ablation 1 — no curriculum (Stage C from scratch)

The curriculum earns its keep on level, and the refit made that cleaner. Every
headline seed beats every control seed by about two points (6.30–6.54 against
4.32–4.42), where the old grid's best control seed at 5.74 came within 0.5 of the
worst headline seed. Two seeds either side, so the gap is worth trusting mainly
because it is large.

The stability half of the old claim did not survive. On the 19 Jul grid the
headline's seed spread was a quarter of the control's (0.26 against 1.66), which
read as the curriculum stabilising training. On the refitted physics it is the
other way round: the control spread is 0.10 and the headline's is 0.25. Neither
number means much at two and three seeds, and that is the lesson — the earlier
spread comparison was reading noise as signal, and it should not have been stated
as firmly as it was.

The protocol caveat is unchanged. Both control seeds stagnation-stopped around 1.1M
steps, so this is "each regime allowed to stop when it stopped improving", not
matched step counts. The W&B curves carry the at-matched-steps read and it does not
change the ordering.

### Ablation 2 — penalty-based constraints instead of masks (F-16)

This is the arm the refit changed, and the change is a correction to what the old
readout claimed rather than to the finding it tests.

The architectural claim is untouched. Masks make illegal actions unreachable; a
penalty makes them expensive. That difference is settled by counting coerced and
illegal executed actions on the full evaluation logs, which is F14's M10, and not
by validation points. Whatever the arm scores, it had to *learn* what masking
provides by construction, and v2's own "99.5% compliant" framing is exactly why
compliance moved out of the reward (F-16).

The scoring claim did not survive. The old readout said the penalty policies end
"below the masked control's 4.91 mean". On the refitted physics they end at
4.522/6.023, a mean of 5.272 against the control's 4.367 — above it, not below.
The arm's own two seeds differ by 1.501 points, which is larger than the distance
between the arms in either grid, so neither ordering was ever supported by two
seeds. The honest statement is that this ablation does not measure a level
difference at 5.6.3's seed budget, and the earlier text overread it.

Two measured numbers below are from the 19 Jul grid and were not re-run for F18:
random play in the penalty world committed about 22.6 violations per race over 20
races (overwhelmingly empty-store attack requests, plus the two-compound breach),
and replaying the better seed's selected policy over 20 races produced 0.00 per
race. Both describe the pre-refit arm. The authoritative post-refit compliance
number is M10, measured over the whole evaluation suite rather than 20 races.

Structural honesty note, pre-registered and unchanged: the pit lane never closes in
live play and the unfitted-compound guard holds in every mode, so the violations
available to this arm are the wet-tyre rules, the two-compound rule and the
SOC-floor attack.

### Ablation 3 — v2's twelve-term reward

The likely publishable negative result arrived on schedule and survived the refit,
though with less room to spare. The arm still has the worst mean on the board
(4.210 against the control's 4.367) and the worst single seed (3.548), and both
seeds again ran to the full 4M ceiling without ever stagnating — the one behaviour
in this study that has reproduced across both physics.

The margin is the part that moved. Against the matched control the gap was 0.98
points and is now 0.16; against the headline it was 2.46 and is now 2.19. The
seeds are also no longer the tight pair they were (3.548/4.872 against 3.815/4.052).
So the claim worth making is the one about the headline, where the gap is large and
stable, and not the one about the control, where it has shrunk into the noise.

The dominance-ratio telemetry shows
why: the twelve terms bury the terminal objective under shaping income the agent
can farm without finishing higher, exactly the F-15/F-17 mechanism (the +0.2
oscillation pump and the pay-to-pit-early grip bonus are both reproduced verbatim
in `senna/env/reward_v2.py`). The reconstruction caveats stand as documented in
`configs/ablations.yaml` — the fuel-penalty magnitude, undercut labelling rule
and ERS-violation trigger are flagged `reconstructed`, and in v2 mode the
position decomposition is the gain/loss pair, not a zeroed v3 `position` key —
but the qualitative conclusion does not hinge on them: heavy shaping hurt, by
about 2.2 points against the headline on the refitted physics and 2.4 on the old.

### Ablation 4 — terminal-only reward

Still the most interesting number in the study, and the one that reproduced best.
With both shaping terms off, the sparse terminal signal alone reached 6.457/5.423,
a mean of 5.940 against the matched control's 4.367 — a 1.57-point margin where the
old grid gave 1.32. Same conclusion, slightly larger.

Where it sits against the headline moved. On the old grid the gap was 0.16 points,
which read as "within noise"; on the refitted physics it is 0.46 (5.940 against
6.397). That is still inside this arm's own seed spread of 1.03, so the fair
reading is that terminal-only stays competitive with the full curriculum without
matching it, rather than the stronger "lands within noise of it" the old text used.

The interpretation is unchanged. At this budget, with masks doing the compliance
work and the horizon a single race, v3's light shaping is not load-bearing; the
shaping terms' defensible role is per-lap credit legibility, the decomposition the
interpretability contract wants, rather than raw performance. Two seeds are not a
theorem — present this alongside the gamma-sensitivity one-liners and the dominance
ratio rather than as a settled claim — but it is a finding worth a section, not a
footnote, and it is now a finding that has held across two different physics.

### Headline — 3 seeds, full curriculum

All three seeds cleared their Stage A and B gates and finished Stage C with tightly
grouped validation scores (6.295 / 6.355 / 6.542); seed 211 reached the ceiling
rather than stagnating. Selection followed the 5.7 rule extended across seeds —
highest validation points, ties to the earlier step, then the lower seed — and
chose **seed 331 at global step 1,769,472: `senna-ppo-70098e9d3425-C-01769472`**,
promoted to `models/headline/` with the triplet verified against the gate log
before copying. This is the model version F09 explains and F10 serves.

The refit barely touched this slate. The mean went 6.396 to 6.397, and seed 331 won
both times. Better physics bought a better simulator, not a better score against it,
which is what should have been expected: the agent is scored inside whichever world
it trained in, so improving that world moves the ground and the agent together. The
number that can move is the sim-to-real error, and that one did (M8).

The previous headline was `senna-ppo-6b6edb78d84e-C-00835584` at 6.517. Test seeds,
the test rival band and every M1–M11 number remain untouched here for F14.
