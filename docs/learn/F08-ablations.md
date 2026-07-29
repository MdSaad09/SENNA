# F08 — Ablations: the evidence base

## What we built and why

F07 ended with a trained agent. The examiner's next question is the one this feature
answers: how do you know your design choices did anything? You believe the academy
works — solo laps first, promotion by observed test, a rulebook enforced by stewards
rather than fines, a three-term briefing instead of a twelve-bullet lecture. Belief is
not evidence. Evidence is running the academy again with exactly one thing changed and
racing the graduates under identical conditions. That is what 5.6.3 specifies: four
ablation arms at a 4M-step ceiling and two seeds each — no curriculum, fines instead
of stewards, v2's old twelve-term reward, and a reward with no shaping at all — plus
the 3-seed headline run under the full curriculum, whose best checkpoint becomes the
model F09 explains and F10 serves.

The feature opened with a bug, found during planning: the action mask never checked
whether a slick compound had a degradation fit for the circuit. At Suzuka, which fits
only MEDIUM and HARD, the agent could pit onto SOFT — a tyre whose physics borrowed
HARD's wear curve while the observation reported full grip forever. No evidence run
starts on an exploitable env, so the mask guard landed first.

Nothing in F08 invents new training machinery. Every arm runs through F07's
`train_run` loop untouched; F08's contribution is worlds to train in (two new env
kwargs), a harness that runs the matrix reproducibly (config overlays, a run ledger),
and selection that picks the headline honestly (validation seeds only, verified
promotion).

## New ideas in this feature

**Ablation study, and the matched control (5.6.3, F-22).** An ablation study removes
or replaces one component at a time and measures the damage; the arm with nothing
changed is the control, the fixed reference every other arm is read against. SENNA
runs all four arms as Stage C from scratch at 4M steps — row 1 of 5.6.3 names that
regime, rows 2–4 are silent, and putting them all in it makes arm 1 (no curriculum,
stock env) a *matched* control: arms 2–4 differ from it on exactly one axis, and the
curriculum question is answered by comparing arm 1 against the headline's curve at
equal global steps. Two consequences follow. The lr/ent schedules keep the global 8M
horizon in every run (the overlay's Stage C budget equals the real Stage C ceiling,
so `run.py`'s sum over stages is unchanged), which means an arm's schedule position
at step t is identical to the headline's — an arm deliberately ends mid-decay at
lr ≈ 1.5e-4, because finishing the decay would confound the treatment with the
learning rate. And selection always evaluates in the default masked, v3-reward env,
so validation points are comparable across arms; the penalty arm's violations are
visible in its training curves, never in its selection score. One arm is absent by
architecture: DQN needs a flat Discrete action space and the env is
MultiDiscrete([6, 4]) by F-18's design — flattening pit and mode into 12 entangled
actions to accommodate the baseline would undo the fix F-18 exists to make
(R-06 documents the exclusion).

**Reward hacking, and the faithful strawman (F-15, F-17).** Reward hacking is a
policy maximising the reward you wrote instead of the outcome you meant. v2's
position terms are the textbook case: +1.0 per place gained, −0.8 per place lost, so
losing P4 and taking it back nets +0.2 — a pump the agent can work by oscillating,
paid for finishing exactly where it started. F05's potential-based term is the fix
(the shaping telescopes to zero over any position cycle), and ablation 3 is the
measurement: rebuild v2's reward and let the same algorithm train against it. The
craft point is fidelity. A reimplementation that quietly fixed v2's bugs would be a
strawman, so the pathologies are reproduced on purpose and pinned by test —
`test_v2_position_terms_pay_the_oscillation_pump` asserts the +0.2. Because the v2
document itself no longer exists, the coefficients come from the master spec's
"v2 says" audit quotes, and the roughly three unquoted values carry a fourth
provenance tag alongside F00's sourced/fitted/stylised: `reconstructed` — our best
reading of a dead document, flagged so the readout carries the caveat.

**Penalised compliance (5.6.3 row 2, F-16, E-01).** F05 taught compliance by
construction: masks for discrete rules, physics clipping for continuous ones, 100%
legal by architecture. Penalised compliance is the alternative SENNA rejected and v2
used: let the illegal request execute, fine it, and hope the policy learns not to
press the button. Ablation 2 rebuilds that architecture as
`F1RaceEnv(constraints="penalty")` — `action_masks()` returns all-True, illegal
requests execute and are counted and fined — with one line drawn in stone: physics
clipping never relaxes. E-01 is conservation, not legality; SOC stays in [0, 4] MJ
and an attack on an empty store still derates in both modes, so the arm isolates
discrete rule-following and nothing else. Mental model: stewards who physically stop
an illegal car versus stewards who wave it through and post the fine — under the
second regime you can finish a race in breach, and the interesting number is how
long the agent spends learning what "illegal" means.

**Config overlays and the write-ahead run ledger.** Two reproducibility mechanisms,
one per half of the harness. An overlay is a derived configs directory — copy
`configs/`, write the arm's env overrides and budget into Stage C, train from the
copy — so each arm's fingerprint differs precisely because its config bytes do: the
run's identity describes the world it trained in, with no arm-specific branch inside
`train_run`. The ledger (`models/runs.json`) is F01's E-12 checkpoint discipline
applied to training runs: the row is written with status `"running"` *before* the
first step, so a crashed or interrupted run is visible as an incomplete row instead
of vanishing — the restart-from-zero resume policy stays honest, and an `attempts`
counter keeps the first try on record.

**Cross-seed selection with verified promotion (5.7, extended).** F07's
`select_checkpoint` picked within one run: best validation points, ties to the
earlier step. F08 extends it across the three headline seeds, adding the lower seed
as a documented last resort so the choice is a pure function of the recorded numbers,
and adds a trust-but-verify step: promotion re-reads the chosen `best/` triplet's
manifest and refuses to copy unless its global step equals the gate log's recorded
selection. The coupling that makes `best/` the selected checkpoint holds only while
`min_improvement_points` is 0.0 — a config edit away from a silent lie — so the
harness checks the claim instead of trusting it.

## The code, guided

Reading order follows the dependency chain: the mask guard, the env variants, the
reconstructed reward, the constants, then the harness and selection.

### masks.py — the unfitted-compound guard

One new reason code and one new keyword. The guard sits inside the `else` branch of
the lane-open check, after the weather rules:

```python
if fitted_slick_actions is not None:
    for action in SLICK_ACTIONS:
        if pit[action] and action not in fitted_slick_actions:
            pit[action] = False
            reasons[f"pit:{action}"] = UNFITTED_COMPOUND
```

`fitted_slick_actions is not None` — the default is None, meaning no guard, which
keeps the ~15 existing direct-call mask tests passing untouched and keeps `masks.py`
free of compound-name knowledge; the env owns the mapping. `for action in
SLICK_ACTIONS` — slicks only, because the degradation fits are per-slick; inter and
wet legality is weather's business. `if pit[action]` first — a slick already masked
by the wet rule keeps its weather reason, because the first rule wins and the
decision card should name the reason that actually bites (a soaked track explains a
banned slick better than a data footnote). The mask-plus-reason-code pattern is
F05's, unchanged, so the explanation layer needs no new case.

Why is this the bug fix, and why a mask? The unfitted slick fell through two
*different* fallbacks that disagreed about the same tyre: `dynamics._compound_lookup`
priced it with the hardest fitted slick's wear curve (so it drove like a HARD), while
`observation.py`'s identity fallback (`a=0, b=1`, so `grip = 1 − 0·age = 1.0`)
reported full grip forever in obs #9, with the generic 40-lap cliff behind it. The
policy could learn "SOFT at Suzuka never degrades" from a state signal that was
fiction. And it is not a sporting rule — it is a hole in our dataset. There is no
correct price for driving a tyre we never fitted, so a penalty would just put a
number on garbage; the option has to not exist. The F06 baselines already shopped
only fitted compounds, so the guard closes the same door on the agent. The viva
answer: **an unfitted compound is a data-availability limit, not a rule the physics
can price, so it is masked structurally with its own reason code (F-16's
architecture), and the guard holds even in the penalty ablation — a fine cannot buy
out missing physics.**

### race_env.py — the wiring and the two variant axes

The guard's env side is one frozen set, built once in `__init__` per the F05
hot-loop rule and handed to `build_mask` by `_ego_mask` with zero per-step work:

```python
self._fitted_slick_actions = frozenset(
    compound_code(name) + 1 for name in self.scenario.available_compounds
)
```

The `+ 1` maps compound codes 0–2 onto pit-head actions 1–3, because action 0 is
stay-out. `build_scenario` already refuses circuits with fewer than two fitted
slicks, so the F05 invariant that no head is ever all-False survives — even the F-20
last-lap forced pit always has a legal target. (`observation.py`'s only change is
renaming `_NO_DEG_A/_NO_DEG_B` public so the v2 reward's grip term shares the same
fallback — two views of an unfitted set can never drift apart.)

Two new keyword-only kwargs carry the ablation arms: `constraints: "mask" | "penalty"`
and `reward_mode: "v3" | "terminal_only" | "v2"`. The defaults reproduce the standing
env bit for bit (`test_default_env_is_unchanged_by_the_variant_kwargs` races the two
lap by lap), and the default path never even reads `ablations.yaml` — the constants
load once at construction, only when a variant asks. The learner-facing half of
penalty mode is two lines:

```python
def action_masks(self) -> np.ndarray:
    if self._constraints == "penalty":
        return np.ones_like(self._mask.flat())
    return self._mask.flat()
```

All-True: MaskablePPO sees no fence. But `self._mask` is still built every step,
because the true mask has a second job — it is the violation detector, and its
reason codes are the vocabulary the violations are counted in. The action door is
`_coerce`, which now splits:

```python
pit, mode = int(action[0]), int(action[1])
mask = self._mask
self._violations_this_lap = {}
if self._constraints == "penalty":
    return self._coerce_penalty(pit, mode)
```

Unpack (MultiDiscrete arrives as an array); judge against the mask the agent
actually sampled under (built at the end of the previous step); clear the per-lap
violation count so `info["violations"]` is always this lap's; delegate. The masked
path below is F05's, unchanged. The penalty path, line by line:

```python
def _coerce_penalty(self, pit: int, mode: int) -> tuple[int, int]:
    mask = self._mask
    if not mask.mode[mode]:
        self._count_violation(mask.reasons[f"mode:{mode}"])
    if mask.pit[pit]:
        return pit, mode
    reason = mask.reasons[f"pit:{pit}"]
    if pit in SLICK_ACTIONS and pit not in self._fitted_slick_actions:
        if reason != UNFITTED_COMPOUND:
            self._count_violation(reason)
        return self._snap_pit(pit), mode
    self._count_violation(reason)
    return pit, mode
```

The mode branch counts but does not snap: an attack on an empty store executes, and
the physics derates it anyway — E-01's clipping does the pricing, the fine lands on
the *request*, which is exactly v2's clip-plus-penalty architecture. A legal pit
passes untouched. An illegal pit's reason comes from the detector's reasons dict —
the same strings the decision cards use, so the training curves and the explanation
layer speak one language. The unfitted-slick branch is the guard holding in every
mode: the request is still snapped (letting it through would reopen the exact
exploit the guard closed), and it is fined only when the reason was a sporting rule
— if wetness banned the slick you pay for the wet-rule breach; if only the data
limit did, you pay nothing, because a missing fit is our gap, not the agent's crime.
Everything else executes and is counted: a last-lap stay-out finishes the race in
breach of the two-compound rule (deterministic in a dry race — the
"otherwise ablation 2 measures nothing" test pins it), a slick pit on a soaked track
executes and the wetness physics prices the laps.

The fine itself is one term in the reward decomposition:

```python
if self._constraints == "penalty":
    terms["violation_penalty"] = (self._violation_penalty
                                  * sum(self._violations_this_lap.values()))
```

−8.0 per breach, from `ablations.yaml` — reconstructed, because v2 quoted −8.0 for
its ERS breach alone and one magnitude for every discrete breach is our documented
reading. `reward_mode` dispatches in `_reward`: `terminal_only` returns
`{"pace": 0.0, "position": 0.0, "terminal": terminal}` — both shaping terms
*reported at zero* rather than dropped, because the decomposition contract says
`info["reward_terms"]` always sums to `total` in every mode, and that contract is
what lets `RewardTermsCallback` iterate keys instead of hard-coding three. The v2
branch swaps in twelve terms fed by `_v2_lap_facts`, a small numpy-only state
accrual gathered *before* the pit swap mutates compound and age — the stint-end grip
must be the outgoing tyre's — plus a running fastest-lap ledger and a pending
undercut check (`state.lap + 1 + window`: judged once `window` full laps after the
stop lap have run).

### reward_v2.py — the twelve terms

Pure functions, one per term, coefficients injected from yaml so the module holds no
numbers. The position pair is the heart of the ablation:

```python
delta = prev_position - position  # positive means places gained
if delta > 0:
    return gain * delta, 0.0
if delta < 0:
    return 0.0, loss * -delta
return 0.0, 0.0
```

`delta` is places gained this lap (positions count down toward P1, so
previous-minus-current is positive on a gain). Gains pay `gain × delta` (+1.0 per
place), losses pay `loss × |delta|` (−0.8 per place), returned as a pair because
v2's decomposition is the gain/loss split, and the asymmetry is the bug: lose one
place (−0.8), regain it (+1.0), net +0.2 for a closed loop. F05's potential-based
term telescopes that same loop to zero (exactly at shaping gamma 1.0; F07 covered
the 0.997 residual), which is the two-line viva contrast this arm exists to measure.

The other terms, each with its reason for existing: `sc_pit_bonus` pays +2.5 for
boxing in the first two laps of a safety car — coaching the textbook move whether or
not it helped this race; `ers_efficiency` pays +0.1 × deployed/E_dep per lap — v2's
"circuit-optimal MJ" denominator was circular, and reading it as the circuit's E_dep
is a flagged reconstruction; `grip_stint_end` pays +0.2 × grip remaining when you
box, a perverse incentive to stop early on barely-worn tyres, kept on purpose;
`undercut_success` pays +0.5 under a labelling rule v2 never published (judged
`undercut_window_laps` after the stop, reconstructed); `ers_violation` fines −8.0 on
any derated lap — the magnitude is quoted, the trigger is reconstructed, because
v2's own trigger was a breach of the 4 MJ/lap cap and that cap does not exist
(F-02, R-03: the never-write table bites even inside the strawman); `tyre_failure`
fines −12.0 on the forced-pit event, not on termination, because a failure here is
+25 s and a stop, never a DNF; `fuel_exhausted` fines −5.0 (magnitude unquoted
anywhere — reconstructed) on a fuel retirement; `fastest_lap_bonus` pays +1.0 for
holding the race's fastest lap inside the points — the rule 2025 abolished (R-01),
judged from lap times because the action that chased it was deleted with the ghost.
Pace and terminal reuse v3's forms, so the arm isolates what v2 *added*.

### configs/ablations.yaml

The constants file the default path never reads. Four blocks: the 4M budget and the
Stage C eval cadence; a `dry_run` tiny profile (the test suite's `tiny_configs`
pattern promoted to the CLI); the `runs` matrix, where each arm is nothing but env
overrides (`{constraints: penalty}`, `{reward_mode: v2}`, …); and the penalty and
reward_v2 coefficients, every line tagged sourced-with-quote or `reconstructed`. The
file enters the fingerprint of ablation runs only — so a later coefficient edit can
never silently break reproduce-by-hash for the promoted headline model.

### ablate.py — the overlay trick

The harness could have re-implemented `train_run`'s tail; instead it changes the
inputs. `overlay_configs` copies `configs/` to `models/overlays/<arm>-s<seed>/`
(keyed by arm *and* seed so one arm's second seed can never rebuild the overlay
under a live run) and edits three things in the copy:

```python
stage_c["env"].update(ablations["runs"][arm].get("env", {}))
stage_c["budget_steps"] = ablations["budget_steps"]
stage_c["eval_every_steps"] = ablations["eval_every_steps"]
```

Same repo configs and same arm always produce the same overlay bytes (F02's
byte-determinism discipline), so the fingerprint `train_run` computes from the
overlay is self-describing: two arms *cannot* share a fingerprint, because their
config bytes differ. `run_ablation` then computes that fingerprint early, mints the
run id, writes the ledger row, and calls
`train_run(from_stage="C", to_stage="C", fresh=True, configs_dir=overlay,
run_tag=f"abl-{arm}", extra_config_files=("ablations",))` — the Stage C branch of
F07's loop provides `best/`, the gate log and selection recording for free.
`--dry-run` maps to the tiny profile, which is how the whole matrix proved itself in
seconds before any real hours burned.

### ledger.py — the row exists before the run

`RunLedger` is a dict of rows behind atomic tmp-plus-rename writes (the `gatelog.py`
pattern). `record_start` writes `status: "running"` with seed, kind, fingerprint,
budget and W&B id before the first env step; `close_run` completes the row from what
the run left on disk — the final manifest's exit reason and the gate log's recorded
selection — rather than from anything held in memory. If the process dies mid-run,
the ledger shows an honest `"running"` row that never completed, and the `attempts`
counter keeps the first try visible when the same id restarts.

### run.py, tracking.py, callbacks.py — the seams

Block-level, because each is a small extension of F07 machinery. `run_identity`
prefixes the run id with the tag (`abl-penalty_constraints-20260719-s101-…`): two
same-day arms with the same seed previously collided on run id and directory, the
plan's finding 6. `--fresh` opens the one legitimate door to a from-scratch Stage C
start (the no-curriculum ablation); starting past A without `--resume` *or*
`--fresh` still raises, so the accident guard stays. `extra_config_files` appends
`ablations` to the fingerprint list for ablation runs only, protecting the
headline's 11-file fingerprint. And the fix for a quiet F07 bug: every manifest's
`wandb_run_id` was null, because `run.py` read it via `getattr(tracker, "run_id",
None)` and no tracker ever had the attribute — a getattr default is a contract
nobody enforces, so nothing failed. `Tracker` now declares `run_id = None` and the
wandb tracker sets it from `run.id`; the ledger requires the field, and a stub-tracker
test pins it end to end. `RewardTermsCallback` iterates whatever keys the env's
decomposition reports (twelve for v2, four for penalty) instead of hard-coding
three, and the dominance ratio is logged only when shaping is nonzero — the
terminal-only arm records `None` honestly instead of |terminal|/epsilon noise.

### selection.py and headline.py — pick, verify, promote

The cross-seed rule is one line:

```python
return max(candidates, key=lambda c: (c.mean_points, -c.step, -c.seed))
```

Best mean validation points; ties to the earlier global step (F07's reasoning —
same measured quality, fewer evals' worth of opportunity to overfit the validation
bank); ties again to the lower seed, so the choice is a deterministic function of
the recorded numbers. `promote_headline` then refuses to copy unless the chosen
`best/` manifest's `global_step` equals the gate log's selected step — finding 7's
fragile coupling, checked instead of trusted — and swaps the triplet into
`models/headline/` atomically with a `promotion.json` naming the `model_version`
F09 and F10 consume. `score_triplet` (behind `make rescore` (named `make eval` until F15)) re-scores any saved
triplet on the validation banks, always in the default masked v3 env. `headline.py`
runs the three seeds and skips completed ones by matching the ledger on
(kind, seed, fingerprint) — never on run id, which embeds its start date; an
overnight interruption must not re-run finished seeds. The seed discipline
underneath is F03's train/validation/test split applied to RL: gates and selection
read the validation banks, and the test bank stays behind F07's loader, which
refuses every consumer literal except `"F14"` — plus a grep test asserting no F08
module even names it.

## How it connects

```
 configs/ ─┬─ ablations.yaml ──overlay──► models/overlays/<arm>-s<seed>/
           │                                   │ fingerprint(11 files + ablations)
           │   seeds.yaml train.ablation       ▼
           │   ledger row ("running") ──► train_run(C, fresh) ── F07 loop, untouched
           │                                   │ env: F1RaceEnv(constraints=…, reward_mode=…)
           │                                   ▼
           │              models/abl-<arm>-<date>-s<seed>-<fp12>/
           │                stageC/{last,best,final}/ · curriculum_gates.json ─► close_run
           │
           └─ headline: 3 seeds, full A→B→C ─► selection (val points, tie→step→seed)
                                                   │ promote (best/ verified vs gate log)
                                                   ▼
                                     models/headline/ ── F09 explains · F10 serves ·
                                                         F14 judges (reserved test bank)
```

Every arm and the headline evaluate in the same default masked v3 env, so one
validation axis compares them all; the readout doc (`docs/results/F08-ablations.md`)
is the committed paper trail, with the penalty arm's expectation pre-registered
before the runs.

## Try it yourself

All commands from the repo root. One caution first: if `models/runs.json` shows a
row with `"status": "running"`, a real arm is training — the Makefile's
one-arm-at-a-time note is real, so hold exercise 4 until it finishes.

1. **Run the variants suite.** `uv run python -m pytest tests/env/test_variants.py -q`
   — 13 tests, a few seconds. Skim the file afterwards and find the pin the feature
   spec demanded: the penalty env must actually permit and count a breach, otherwise
   ablation 2 measures nothing. You'll know it worked when all 13 pass and you can
   name which test races the default env against the explicit-kwargs env lap by lap.

2. **See the mask guard speak.** With `uv run python`:

   ```python
   from senna.env import F1RaceEnv
   env = F1RaceEnv("japanese_grand_prix")
   _, info = env.reset(seed=7)
   print(info["mask"]["pit"])      # [True, False, True, True, False, False]
   print(info["mask"]["reasons"])  # pit:1 -> compound_unfitted_for_circuit
   ```

   Suzuka fits only MEDIUM and HARD, so SOFT (action 1) is off the table from reset.
   You'll know it worked when the reasons dict names `compound_unfitted_for_circuit`
   for pit:1 and weather reasons for inter and wet.

3. **Watch a violation get counted.** Still in `uv run python`:

   ```python
   import numpy as np
   from senna.env import F1RaceEnv
   env = F1RaceEnv("bahrain_grand_prix", constraints="penalty")
   env.reset(seed=7)
   print(env.action_masks().all())   # True — the learner sees no fence
   env._state.soc_mj[0] = 0.0        # white-box: drain the battery
   env._mask = env._ego_mask()       # rebuild the detector to match
   _, r, _, _, info = env.step(np.array([0, 2]))  # stay out, attack anyway
   print(info["violations"], info["reward_terms"]["violation_penalty"])
   ```

   You'll know it worked when you see `{'soc_below_attack_floor': 1}` and −8.0 — and
   when you can explain why `info["energy"]["deploy_mj"]` is still small: the fine is
   on the request, the derate priced the physics (E-01 never relaxed).

4. **Dry-run an arm.**
   `uv run make ablate RUN=penalty_constraints DRY=1 VEC=dummy WORKERS=2 WANDB=disabled`
   — about 40 seconds on the tiny profile. Then read `models/runs.json` and the new
   run dir's `curriculum_gates.json`. You'll know you understand the harness when
   you can point at the row that existed before training started (its `started_at`
   versus the gate log's first eval), say why the run dir starts with
   `abl-penalty_constraints-`, and find the overlay whose bytes made this arm's
   fingerprint differ from `no_curriculum`'s.

5. **Try to fix v2, and get refused.** Edit `configs/ablations.yaml`: set
   `position_loss` to `-1.0` (symmetric with the gain), then run
   `uv run python -m pytest tests/env/test_reward_v2.py -q`. You'll know it worked
   when two tests fail — the quoted-formulas check and the oscillation pump, which
   now nets 0.0 instead of +0.2. You just repaired v2's bug, and the suite refused
   the repair, because a faithful strawman must stay broken. Revert.

## Check yourself

1. The unfitted-compound rule is enforced by a mask even in the penalty ablation,
   while every sporting rule switches to fines. Defend the inconsistency.

2. What exactly does ablation 2 measure during training, what will F14 measure that
   it cannot, and why is its selection score comparable with the other arms'?

3. Show the arithmetic of the F-15 oscillation pump under v2's coefficients, and
   explain in one sentence why v3's position term is immune.

4. Defend the experiment design: why do all four ablations run Stage C from scratch
   at 4M steps, and why does the lr schedule keep the 8M horizon in a 4M run?

5. A run directory named `abl-reward_v2-20260721-s211-9f3c…` exists on disk. Walk
   the chain that lets you rebuild that exact run, and name the two places the
   harness checks a claim instead of trusting it.

---

### Answers

1. Not an inconsistency: the sporting rules have a defined outcome when broken — the
   race finishes in breach, the wetness physics prices a wrong tyre — so a penalty
   arm can execute them and measure the cost. An unfitted compound has no defined
   outcome at all: the circuit has no degradation fit, so the sim would be pricing
   fiction (HARD's wear curve under an observation claiming full grip forever). A
   data limit cannot be bought out with a fine; the option must not exist, so
   `_coerce_penalty` still snaps it and counts no violation unless a sporting rule
   also forbade it.

2. During training it counts every illegal request in `info["violations"]` under the
   mask's reason codes and fines each −8.0 — the observable breaches being the wet
   tyre rules, the two-compound rule and the SOC-floor attack — so the curves show
   how much learning capacity goes into "don't press the illegal button" (F-16's
   question). It cannot measure the final-policy compliance gap; that is F14's job.
   Its selection score is comparable because selection always evaluates in the
   default masked v3 env: the arm is judged on race quality under masking, with its
   violations visible only in training telemetry.

3. Lose a place: −0.8. Regain it: +1.0. Net +0.2 for a closed loop, so oscillating
   with a rival is directly profitable — that is F-15's documented pump, reproduced
   by `test_v2_position_terms_pay_the_oscillation_pump`. v3's term is
   `gamma·Φ(s′) − Φ(s)` with `Φ = −0.1 × position`, which telescopes over any cycle
   to (near) zero, so no sequence of position swaps can mint reward (F05; the
   0.997-gamma residual is F07's documented mismatch).

4. Row 1 of 5.6.3 names the from-scratch Stage C regime; rows 2–4 are silent, and
   running them in the same regime makes arm 1 a matched control — each other arm
   differs from it on exactly one axis, and the curriculum's value is read off arm 1
   versus the headline at equal global steps. Threading arms 2–4 through the
   curriculum instead would need invented stage ceilings and would confound every
   comparison with the gate schedule. The schedule keeps the 8M horizon so an arm's
   lr/ent position at step t equals the headline's; an arm ending mid-decay at
   lr ≈ 1.5e-4 is the price of that, paid deliberately, because completing the decay
   would make "different objective" and "different learning rate" inseparable.

5. The run id's fingerprint hashes the overlay configs the run trained from, and the
   overlay is deterministic: same repo configs plus same arm produce the same bytes,
   so `make ablate RUN=reward_v2 SEED=211` rebuilds the identical world (the ledger
   row carries seed, kind, fingerprint, budget and the W&B id; the manifest adds the
   git commit). The two verifications: the ledger writes the row before training and
   completes it from what the run left on disk (a crash is visible, never silent),
   and `promote_headline` re-checks that `best/`'s manifest step equals the gate
   log's recorded selection before anything is copied.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Ablation study and the matched control (5.6.3, F-22) | F08 | Change one component per arm and measure against a control that changes nothing; SENNA runs all four arms as Stage C from scratch at 4M with the global 8M lr horizon kept, so arms differ from the control on exactly one axis and from the headline only in the curriculum. |
| Reward hacking and the faithful strawman (F-15, F-17) | F08 | A policy maximising the written reward, not the intent (v2's +1.0/−0.8 position pair pays +0.2 per oscillation); the ablation rebuilds v2's reward with its pathologies pinned by test, unquoted values tagged `reconstructed`. |
| Penalised compliance vs masking (5.6.3 row 2, F-16, E-01) | F08 | The `constraints="penalty"` variant reports all actions legal, executes illegal requests and fines them −8.0 under the true mask's reason codes — while physics clipping never relaxes, so only discrete legality changes architecture. |
| Data limit vs sporting rule (F08 mask guard) | F08 | A slick with no degradation fit is masked structurally with the `UNFITTED_COMPOUND` reason in every constraints mode — missing physics has no price, so no fine can buy it out, unlike sporting rules a penalty arm may breach and pay for. |
| Config overlays and the write-ahead run ledger | F08 | Each arm trains from a derived copy of configs/ whose bytes make its fingerprint self-describing, and models/runs.json gets its row (status "running") before the first step, so interrupted runs are visible and restarts honest. |
| Cross-seed selection with verified promotion (5.7, F08) | F08 | Best validation points across seeds, ties to the earlier step then the lower seed; promotion re-verifies the chosen best/ manifest against the gate log before atomically copying to models/headline — check the claim, never trust the coupling. |
