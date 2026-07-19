# F07 — Training: MaskablePPO and the curriculum

## What we built and why

Everything before this feature was preparation. F05 built the race the agent lives in,
F06 built the opponents and the measuring apparatus. F07 is the feature where the agent
actually learns — and, just as importantly, where the learning is provable: promotion
happens by passing tests, stalled training stops costing compute, and the result ships
in a form that behaves identically when F10 serves it.

Race terms first. You would not throw a rookie into a wet Spa with 21 rivals and a red
flag. You start them alone on an empty Monza in the dry, until they can lap within a
whisker of what the pit wall computes as the best possible race. Then you give them a
field and safety cars and ask them to beat a competent engineer more often than not.
Only then do you hand them the full calendar — 24 circuits, weather, red flags, the
lot. That is the 5.7 curriculum: Stage A solo fundamentals, Stage B competition, Stage
C the full problem. The critical design rule is *how* a driver moves up. Never by hours
in the car — always by passing an observed test. Each stage has a step budget, but the
budget is a ceiling, not a schedule (R-12): the stage ends the moment its competence
gate passes, and hitting the ceiling without passing is recorded as exactly that, a
`budget_stop`, never a promotion (F-21).

The training itself is MaskablePPO from sb3-contrib — PPO that respects F05's action
masks — running 12 copies of the env in parallel, with every hyperparameter in
`configs/training.yaml` carrying its 5.6.1 reasoning. Because F06 measured 18,477 env
steps/s (5.6.2, OQ-2), the whole 8M-step ceiling costs minutes on Saad's Mac, so the
design optimises for the paper trail: frozen seed banks, a gate log that survives a
crash, and checkpoints saved as complete triplets whose hashes are their identity
(F-23). One process runs A then B then C on one global step axis; one W&B chart shows
the whole career.

## New ideas in this feature

**PPO, and what MaskablePPO adds (5.6.1, F-16).** PPO (proximal policy optimisation)
is the workhorse policy-gradient algorithm: collect a batch of experience with the
current network, estimate for each action how much better it turned out than the value
head predicted (the advantage), then nudge the network to make above-average actions
more likely — with the nudge *clipped* so no single batch can drag the policy far from
the one that collected the data. That clip is the "proximal" part, and it is why PPO is
stable enough to leave running unattended. MaskablePPO is the same algorithm with F05's
action mask applied inside the probability distribution: masked logits are set to
minus infinity, so an illegal action has probability zero both when sampling rollouts
and when computing the update's log-probabilities. The operational fact worth knowing:
no wrapper is needed. sb3-contrib fetches the masks itself by calling
`env_method("action_masks")` down through the vec stack, and both VecNormalize and
SubprocVecEnv forward that call, so the compliance architecture rides along untouched.
Mental model: a coach who only ever grades you on moves the rulebook allowed — the
agent never spends a single gradient learning what "illegal" means, which is the
trainer-side half of the F-16 masking-not-penalties argument from F05.

**Vectorised training and VecNormalize (5.6.1).** SubprocVecEnv you met on the F06
stopwatch — N env copies in worker processes, stepped in lockstep. VecNormalize is the
wrapper above them that keeps a running mean and variance per observation slot and
hands the network z-scored inputs, so slot 0 (lap fraction) and slot 16 (battery in MJ)
arrive in comparable units whatever the current stage's distribution looks like.
SENNA sets `obs: true, reward: false`: observations vary in scale, but the reward is
hand-scaled by 5.5.4 and a running reward normaliser would quietly shrink the sparse
terminal signal relative to the dense shaping — the exact balance the dominance ratio
exists to guard. The subtlety that matters later: those running statistics are
*learned state*. The network's weights are meaningless without the statistics they were
trained behind, which is why F-23 exists.

**The checkpoint triplet (F-23).** A SENNA checkpoint is never just weights. It is
three files saved atomically as one unit: `model.zip` (the network), `vecnormalize.pkl`
(the observation statistics), and `manifest.json` (config fingerprint, git commit,
stage, step, seeds, library versions — and the sha256 of the other two files, so the
statistics' own hash is part of the model's identity). The failure mode this kills is
silent: load weights without their statistics and the network receives raw
observations where it expects z-scores. Nothing throws. It just plays confidently
wrong, and you would only notice weeks later in F10 as an inexplicably bad served
model. The viva answer: **a VecNormalize policy is a function of normalised inputs, so
the statistics are part of the model, not part of the training run; F-23 ships them in
every checkpoint, hashes them into the manifest, and the round-trip test proves a
reloaded triplet gives the identical action for the identical observation.**

**Competence gates, and budgets as ceilings (5.7, F-21, R-12).** F06 built the two
reference points — the Stage A `solo_reference` and the Stage B baselines; F07 builds
the machinery that tests against them. A step schedule says "1.5M steps, then move up";
a competence gate says "prove it, on frozen seeds, against a fixed bar". SENNA's gates
are pure functions of eval histories in `gates.py`, and their signatures simply have no
budget parameter — advancing on step count is not forbidden by policy, it is
unrepresentable in the code. The budget appears only in the loop, as the ceiling on
`learn()`, and a ceiling hit writes `budget_stop` to the gate log while a pass writes
`transition`. Mental model: a karting licence upgrade. The season ending early does not
give you the next licence; only the observed test does, and the examiner's clipboard
(`curriculum_gates.json`) records which one happened. The viva answer: **gates instead
of schedules because a step count measures effort, not competence (F-21); the budgets
stay as ceilings so a run that never becomes competent stops spending compute, and the
log distinguishes the two exits so a ceiling stop can never masquerade as a pass
(R-12).**

**The two gammas (F-15, 5.5.4).** Gamma is the discount factor: a reward t laps in the
future is worth gamma^t now. F05's position shaping telescopes *exactly* at the
shaping gamma of 1.0 — that is what makes it provably policy-invariant. But PPO trains
with gamma 0.997 (5.6.1), because an undiscounted value target over a 70-lap horizon
is needlessly high-variance, while 0.997^69 ≈ 0.81 keeps lap 1 relevant at the flag.
At mismatched gamma the Ng-Harada-Russell invariance holds approximately, not verbatim:
each lap leaks a residual of order (1 − 0.997) × 0.1 × position, a few thousandths of
a reward unit. This is a conscious, documented choice — the comment block on
`ppo.gamma` in `training.yaml` names it, and gamma 1.0 and 0.999 are one-line F08
sensitivity runs if an examiner wants evidence. The viva answer: **the master spec's
0.997 wins for value-estimation variance; the cost is that the potential-based shaping
is approximately rather than exactly policy-invariant, the residual is quantified at
about 0.0003 per lap against a ±0.5-scale pace term, and the matched-gamma run exists
as an ablation to show the choice is not load-bearing.**

## The code, guided

The feature is the new `senna/train/` package, three new configs, and a small set of
env extensions. Reading order follows a training run: what world each stage builds,
what the constants say, how a gate decides, how a decision is evaluated and logged, and
finally the loop that drives it all.

### race_env.py and observation.py — the stage toggles

The env grew three keyword-only kwargs — `solo`, `weather`, `hazards` — whose defaults
reproduce the F06 env bit for bit; `test_default_env_is_unchanged_by_the_new_kwargs`
races a default env and an explicit-kwargs env lap by lap on one seed and demands
identical observations the whole way, so no RNG draw appeared or vanished on the
default path. Each toggle switches
off a mechanism at its source rather than papering over it:

```python
if self._hazards == "none":
    return False, events.GREEN  # no roll, so the RNG stream is untouched
```

Under Stage A's `hazards: none`, `_resolve_track_status` returns green before any dice
are thrown — skipping the roll, not discarding the result, so the remaining streams
stay aligned. `weather: "dry"` does the same in `_resolve_weather` (wetness pinned at
zero from reset, no Markov step), and `hazards: "sc_vsc"` zeroes `_max_red` at
construction because the red flag first appears in 5.7's Stage C row. Tyre failure
under `none` swaps the hazard roll for the deterministic cliff cap — the same rule the
F06 twin already used, so Stage A's only stochastic residue is pit service time.

The one real design change is the solo reward, and it earns line-by-line attention:

```python
terminated = bool(state.lap >= self.total_laps or state.retired[ego])
# solo, the position and terminal terms are constants, so pit loss must enter
# through the pace term or stops are free (5.7 Stage A; F07 decision 1)
pace_time_s = float(lap_time[ego]) if self._solo else float(racing_time[ego])
terms = self._reward(prev_position, pace_time_s, terminated)
```

In the full env the pace term is fed `racing_time` — pit loss excluded — because a stop
already costs you through the position term and the terminal points. Solo, there is no
one to lose position to: the position potential is a constant and the terminal is fixed
at P1's points, so with the literal 5.5.4 wiring a pit stop would cost *nothing* and
Stage A would graduate a pit-happy agent that Stage B has to break. The fix charges
`lap_time` (racing plus pit) to the pace term only when `solo=True` — a documented
divergence from the 5.5.4 table (F07 decision 1), pinned by
`test_solo_reward_pace_term_prices_the_pit_stop`, which asserts the return difference
across a stop equals w_p · pit_loss / s_ref to within the service-time noise. This is
also exactly what the Stage A reference charges (stint tables plus mean pit loss per
stop), so the gate compares like with like.

`observation.py` gets a two-line guard: slots 1 and 2 divide by `n_cars - 1`, which is
zero in a solo field, so both now divide by `max(n_cars - 1, 1)` — the identity
whenever there are two or more cars.

### The three configs

`training.yaml` is the 5.6.1 hyperparameter table transcribed with its reasoning as
comments — this file is the single tuning surface, and the interpretability contract
means every number explains itself. Three entries deserve your eyes: the `gamma: 0.997`
block that documents the conscious mismatch from the new-ideas section; `schedules:
horizon: global`, which decays the learning rate over the *summed* 8M ceiling rather
than per stage (a per-stage decay would jump the learning rate back up at every early
gate exit — precisely the moment the observation distribution shifts); and
`normalize.reward: false` with its dominance-ratio justification.

`curriculum.yaml` is the 5.7 stage table as data: per stage, the circuits, the env
kwargs (`{solo: true, weather: dry, hazards: none}` for A, and so on), `rival_band:
train` (E-06 — the test band never trains), the budget ceiling, the eval cadence, and
the gate thresholds. The cadence is not arbitrary: 49,152 = 8 rollouts of 6,144
(512 steps × 12 workers), so evaluations land on rollout boundaries; Stage C doubles
it because each of its evals rolls 240 validation races.

`seeds.yaml` freezes 1,044 seeds under a dated `frozen_on` header — the E-14 discipline
applied to RL: editing this file after a result exists is seed-shopping, and the viva
reads the header the way it reads `data_split.yaml`'s. The banks are pairwise disjoint
(a test proves it), and the Stage C *test* bank is reserved for F14 mechanically, not
by convention — more below.

### gates.py — the decisions

Pure functions of eval histories, numpy and dataclasses only, no env, no SB3 — which
is what lets the tests drive them with hand-built histories. The plateau rule first:

```python
best_before = max(returns[:-window])
window_best = max(returns[-window:])
improvement = (window_best - best_before) / max(abs(best_before), denominator_floor)
return improvement < min_improvement, improvement
```

Best of the last three evals against the best of everything before them. The naive
reading — compare consecutive evals — passes a policy still gaining 0.9% every single
eval, because each step is under the 1% bar while the window compounds to ~2.7%. The
best-of-window reading keeps training on that slow creep
(`test_stage_a_plateau_is_not_fooled_by_slow_creep`). The `denominator_floor` is a
divide guard for returns near zero, sourced from `curriculum.yaml` like every other
threshold — a default argument here would be an inline constant wearing a disguise.

`stage_a_gate` demands plateau AND time-bar on the same eval, and it scans history
prefixes so that once any prefix passes, the decision holds even if later evals regress
— training stops on a pass, so a decision that could flap on a noisy extra eval would
be a decision you cannot trust (`test_stage_a_gate_holds_once_triggered`). The time
bar itself:

```python
delta_frac = (latest.mean_race_time_s - reference_time_s) / reference_time_s
anomaly = "beats_reference_beyond_tolerance" if delta_frac < -time_tolerance else None
time_ok = delta_frac <= time_tolerance and latest.dnf_count == 0
```

One-sided, by documented choice: the solo reference is near-optimal, not provably
optimal (its energy is greedy per lap), so an agent *faster* than it should pass — but
a beat beyond 1.5% smells like a physics or reference bug, so it passes with a named
anomaly flag that surfaces in the log rather than being quietly celebrated. The
`dnf_count == 0` clause is a recorded strengthening of 5.7: a DNF'd solo race corrupts
the mean-time comparison, and requiring a clean bank can only delay an exit, never
fake one.

Stage B's unit is one paired race:

```python
if agent_dnf and baseline_dnf:
    return False, 0
delta = baseline_position - agent_position
if agent_dnf:
    return False, delta
if baseline_dnf:
    return True, delta
return agent_position < baseline_position, delta
```

Every branch leans against the agent: both-DNF is no evidence and counts as not-ahead,
a finisher beats any DNF, and an equal classification is a loss. `stage_b_gate` then
refuses anything but exactly 200 pairs — a silently dropped seed would bias the
finish-ahead rate, so it fails loudly instead. Stage C is a stagnation clock
(`stage_c_stop`: stop once the best validation score is 1M steps old, strict
best-so-far), and `select_checkpoint` takes the highest validation points with ties
broken toward the *earlier* step — same measured quality, less opportunity to have
overfitted the validation bank.

### seeds.py and gatelog.py

`seeds.py` loads the banks, and `load_banks` simply never returns the Stage C test
bank — it is absent from the dataclass. The only door to it checks its caller:

```python
def load_reserved_test_bank(configs_dir=None, *, consumer: str) -> dict:
    if consumer != "F14":
        raise SeedBankReservedError(...)
```

Held-out means mechanically unreachable, not politely labelled (E-06's discipline,
applied to seeds; `test_the_test_bank_loader_refuses_f07` pins it).

`gatelog.py` is the `curriculum_gates.json` writer (F-21's interpretability-contract
row): thresholds echoed verbatim so the file reads without the yaml beside it, every
eval appended and flushed by atomic tmp-plus-rename the moment it happens (a crashed
run keeps its trail), and `transition` and `budget_stop` as separate fields so the two
kinds of stage exit can never be confused.

### checkpoints.py — the triplet on disk

`save_triplet` writes model, statistics and manifest into a sibling `.tmp` directory
and swaps it in whole, so a triplet is never observable half-written; the manifest is
stamped with the sha256 of both artifacts before the swap (F-23's "the statistics'
hash is part of the model version record"). `load_triplet` is the other half of the
contract: rehydrate the statistics onto a fresh vec env, set `training=False` so they
freeze, and the round-trip test demands the identical deterministic action for the
identical observation. `model_version()` mints
`senna-ppo-{fingerprint[:12]}-{stage}-{step:08d}` — fingerprint first, so the string
F10 stores agrees with the env config hash by construction.

### tracking.py — the W&B seam

The only module in the package allowed to import wandb (F-26 — the sibling of the
fastf1-under-`senna/data` rule, and `test_wandb_is_imported_only_in_tracking` greps the
whole package to prove it). A `Tracker` base class no-ops everything, the real one
wraps a wandb run, `mode: auto` goes online only when an API key exists, and a failed
init degrades to the no-op with a warning — telemetry must never kill a training run.
The last piece is a ~15-line SB3 `KVWriter` that forwards every logger dump
(`train/approx_kl` and friends) to the tracker, because tensorboard is not a
dependency and wandb's stock SB3 callback needs it.

### evals.py — what a gate evaluation actually runs

Stage A is the simple one: one solo env, the 100 frozen seeds, mean return and mean
race time — a pure function of the policy, which is what makes plateau comparisons
across evals honest. The bar it compares against is F06's `solo_reference`, and this
is where tests-first paid for itself. The property test rolls the reference's *own
plan* through a solo green-twin env and demands the rolled time equal the table cost:

```python
# the twin zeroes noise and takes pit service at the mean, so any seed lands on the
# table's cost — the exactness that makes the 1.5% Stage A time gate meaningful
assert rolled.race_time_s == pytest.approx(reference_time_s, abs=0.5)
```

It failed — and the failure was a latent F06 bug. The oracle's `_plan_table_cost`
credited the pit lap to the *new* compound at age 0, but the env runs that lap on the
outgoing tyre and fits the new one at the lap's end: roughly a 0.8 s bias per stop
that nothing in F06 could see, because F06 only ever *ranked* plans with the tables
and re-rolled the finalists anyway. The moment a gate compared a rolled time against a
table number, the off-by-one mattered. The fix realigns the stint boundaries with how
`PlanPolicy` executes:

```python
for out, name in plan.stops:
    cost += tables[compound][start_lap, out]        # was: out - 1
    compound, start_lap = compound_code(name), out + 1   # was: out
```

Stage B is the pairing harness. `record_stage_b_traces` runs the EngineerHeuristic
live in the Stage B world once per run, captures each race as an F06 EventTrace, and —
the detail that makes the comparison clean — stores as the baseline's result *its own
twin roll*, not the noisy live recording, so both sides of every pair face identical
deterministic physics. You already know from F06 why sharing a seed is not sharing a
race: RNG consumption is policy-dependent. Pairing on recorded twins is that lesson
applied to evaluation, and it is decision A-06 in the plan. The strongest single pin
is `test_stage_b_pairing_self_pair_is_a_tie`: the heuristic replayed against its own
trace must land exactly level — not ahead, delta zero. A recording that DNFs before
the flag (`recorded_trace()` refuses it) is replaced from the frozen overflow bank in
order, and every substitution is written to the gate log; an exhausted overflow raises,
because silence would bias the finish-ahead rate. The viva answer: **Stage B pairs on
EventTraces rather than raw seeds because a shared seed diverges into different events
the moment two policies first differ; recording the baseline's races once and replaying
the agent on the frozen twins makes every pair a genuinely controlled comparison, and
the self-pair-is-a-tie property is the proof the harness adds no bias of its own.**

`Sb3Policy` at the bottom is the adapter that lets the trained network wear F06's
`StrategyPolicy` protocol: apply the frozen VecNormalize statistics to the obs, predict
deterministically with the mask passed through. It is deliberately the only place
training statistics touch a gate evaluation.

### envs.py — workers, circuits and episode seeds

`assign_circuits` maps the stage's circuit list onto workers by pure arithmetic on the
yaml order (Stage A: 12 × Monza; Stage B: six circuits twice; Stage C:
`circuits[i::workers]`), so the assignment reproduces from configs and lands in every
manifest. `CircuitCycler` is the wrapper that owns what SB3 does not: SB3 seeds only
the *first* reset of each worker, so the cycler turns that one anchor into a stream —

```python
def reset(self, *, seed=None, options=None):
    if seed is not None:
        self._episode_rng = np.random.default_rng(seed)
    self._index = (self._index + 1) % len(self._envs)
    episode_seed = int(self._episode_rng.integers(2**31 - 1))
    return self._envs[self._index].reset(seed=episode_seed, options=options)
```

— every later episode's seed derives from the anchor, so a whole stage is reproducible
from the stage seed alone (5.5.5 applied per episode), and a worker hosting several
circuits rotates through its pre-built envs instead of rebuilding them. `stage_venv`
assembles worker functions, wraps with Monitor and VecNormalize (fresh for Stage A, or
`VecNormalize.load` to carry the previous stage's statistics — 5.7's continuity
choice), and contains one guard worth noticing: any `rival_band` other than `"train"`
is refused outright, so editing `curriculum.yaml` is not enough to train on the E-06
test band — the code guard mirrors the seed bank's.

### model.py and callbacks.py

`build_model` is `training.yaml` handed to the MaskablePPO constructor — the 5.6.1
table as keyword arguments, CPU device because the policy is tiny. The interesting
work lives in the callbacks. `ScheduleCallback` exists because of an SB3 sharp edge:
`progress_remaining` re-anchors at every `learn()` call, and this run calls `learn()`
once per stage — the spec'd linear decays would restart three times. So the callback
drives both decays off the true global step:

```python
frac = min(1.0, self.model.num_timesteps / self._horizon)
lr = self._lr0 + frac * (self._lr1 - self._lr0)
self.model.lr_schedule = lambda _progress: lr
self.model.ent_coef = self._ent0 + frac * (self._ent1 - self._ent0)
```

The lambda swallows SB3's per-learn progress and returns the globally-scheduled value;
`ent_coef` is a plain float in SB3, so its decay has to be poked in the same way.
`RewardTermsCallback` keeps per-worker running sums of the three reward terms, logs
per-episode means each rollout, and computes the 5.5.4 dominance ratio —
|terminal| over |shaping|, expected around 3 — both per rollout and run-level for the
manifest. It resets its partial sums at each stage boundary, because a gate pass aborts
`learn()` mid-episode and the fragments must not leak into the next stage's means.

`GateEvalCallback` is where a review finding lives. `num_timesteps` is global and
cumulative (we pass `reset_num_timesteps=False`), so a cadence like "evaluate every
time `num_timesteps % every == 0`-ish from zero" would, at Stage B entry (step 1.5M),
believe itself roughly 30 evals behind and burst-run 30 back-to-back 200-race
evaluations. The spec-auditor caught it; the fix anchors the counter at training
start:

```python
def _on_training_start(self) -> None:
    self._next = self.model.num_timesteps + self._every
```

`test_gate_eval_cadence_anchors_to_the_stage_entry_step` steps a fake model from 1.5M
and asserts exactly one eval, one full cadence after entry. On each eval the callback
saves a `last/` triplet, runs the stage's evaluator, logs the `gate/*` series, updates
Stage C's `best/`, and — the R-12 mechanism in one line — returns `False` on a pass,
which is how an SB3 callback ends `learn()` early.

### run.py — the loop

`build_evaluator` closes over each stage's eval history and returns an
`evaluate(step) -> GateDecision` that also appends its numbers to the gate log — the
gates see history, the loop sees decisions, the JSON sees everything. `train_run` is
the curriculum: load configs, fingerprint the eleven files a run is reproducible from,
mint the run id, then per stage build the venv, point the model at it, and call
`learn(budget, reset_num_timesteps=False)` with the four callbacks. Two lines carry
stories. The first came out of review:

```python
# the ctor and load paths call set_random_seed, which re-seeds the env with the
# run seed — re-issue the stage seed so the disjoint-stream design (seeds.yaml
# train.stage_offset) and the manifest's stage_seed entry stay true
venv.seed(seed + stage_offset[stage])
```

MaskablePPO's constructor and its `load()` both call `set_random_seed`, which quietly
re-seeds the attached env with the *run* seed — so a resumed stage would have trained
on Stage A's episode anchors while its manifest recorded a `stage_seed` that was never
applied. The code-reviewer traced it; the stage seed is now re-issued after model
setup. The second is the exit protocol: after `learn()` returns, if the gate never
passed and the last eval is stale, the loop calls `gate_cb.run_eval()` directly — a
ceiling exit still ends with a real, logged evaluation — then writes `transition` or
`budget_stop` accordingly, saves the `final/` triplet, and hands the VecNormalize
statistics path to the next stage (or not: `carry_across_stages: false` is F08's
re-warm ablation, honoured here). The schedule horizon is always the full 8M even for
a partial run, so a resumed Stage B sits on the same decay line an uninterrupted run
would have had. One idiom to notice: the `manifest`/`save_to` helpers bind
`stage=stage` and friends as keyword defaults, because the loop rebinds those names
next stage and a late-bound closure would silently checkpoint the wrong one.

The Makefile's `make train` is a passthrough to `python -m senna.train.run` with
`SEED/FROM/TO/RESUME/STEPS/WANDB/WORKERS/VEC` — run it under `uv run` so the venv's
python is on PATH.

## How it connects

```
 configs: training.yaml (5.6.1) · curriculum.yaml (5.7) · seeds.yaml (frozen banks)
      │
      ▼
 run.py stage loop  ── A ──► B ──► C     (one process, one global step axis)
      │ per stage
      ├─ envs.stage_venv ─► 12 × [F05 F1RaceEnv + F06 rivals] ─ VecNormalize
      ├─ MaskablePPO.learn(ceiling)  ◄─ masks fetched through the vec stack (F-16)
      │      callbacks: schedules · reward terms/dominance · throughput · gate eval
      ├─ evals.py ─► Stage A: solo bank vs F06 solo_reference
      │             Stage B: agent replayed on recorded heuristic twins (A-06)
      │             Stage C: validation points, train band only (E-06)
      ├─ gates.py ─► GateDecision ─► curriculum_gates.json (F-21)
      └─ checkpoints ─► models/<run>/stageX/{last,best,final}/ triplets (F-23)
                              │
                              ▼
        F08 ablations & headline seeds · F09 surrogate distils the policy ·
        F10 serves the frozen triplet · F14 quotes it against the reserved test bank
```

F07 consumes everything F05 and F06 built and produces the artifact the rest of the
project revolves around: a reproducible run directory whose triplets F09 explains,
F10 serves, and F14 judges.

## Try it yourself

All commands from the repo root.

1. **Run the F07 suite.** `uv run python -m pytest tests/train -q`. It covers the
   gates on hand-built histories, the checkpoint round-trip, the pairing harness and
   the wiring smoke. You'll know it worked when 25 tests pass in well under a minute —
   note how much of a training feature tests without ever training.

2. **Train a real Stage A smoke.**
   `uv run make train STEPS=5000 TO=A WORKERS=2 VEC=dummy WANDB=disabled` — about five
   seconds. (`TO=A` stops after Stage A; the dev cap applies per stage, so without it
   the run would continue into Stage B's 200-race trace recording.) Then read
   `models/<run>/curriculum_gates.json`. Predict before you look: gate pass or budget
   stop? You'll know you understand it when you can explain why the stop is at step
   5,120 rather than 5,000 (SB3 collects whole 1,024-step rollouts: 512 × 2 workers),
   why `transition` is null while `budget_stop` is set, and why there is exactly one
   eval row even though 5,120 never reached the 49,152 cadence — the loop's
   stage-exit rule guarantees every exit is preceded by a real, logged evaluation.

3. **Feel the frozen-seed discipline bite.** Delete one seed from the `stage_a` bank
   in `configs/seeds.yaml` and run
   `uv run python -m pytest tests/train/test_seeds.py -q`. You'll know it worked when
   `test_seed_banks_are_sized_and_pairwise_disjoint` fails on the bank size — the
   banks are contract, not convenience, and any edit after training starts is
   seed-shopping by definition. Revert.

4. **Try to steal the F14 test bank.** Run
   `uv run python -c "from senna.train.seeds import load_reserved_test_bank; load_reserved_test_bank(consumer='F07')"`.
   You'll know it worked when `SeedBankReservedError` names E-06 at you. Change the
   consumer string to `"F14"` and it hands over 480 seeds — the discipline is
   mechanical, not decorative.

5. **Round-trip a triplet by hand (the F-23 contract).** After exercise 2, run this
   with `uv run python` from the repo root:

   ```python
   from pathlib import Path
   from stable_baselines3.common.monitor import Monitor
   from stable_baselines3.common.vec_env import DummyVecEnv
   from senna.env import F1RaceEnv
   from senna.train.checkpoints import load_triplet

   run = sorted(Path("models").iterdir())[-1]
   venv = DummyVecEnv([lambda: Monitor(
       F1RaceEnv("italian_grand_prix", "2026", solo=True, weather="dry", hazards="none")
   )])
   model, venv = load_triplet(run / "stageA" / "final", venv)
   obs = venv.reset()
   mask = venv.env_method("action_masks")[0]
   action, _ = model.predict(obs, action_masks=mask, deterministic=True)
   print("action:", action, "| training:", venv.training)
   ```

   You'll know it worked when it prints the same action on every run and
   `training: False` — the statistics came back frozen, the policy is deterministic,
   and the mask arrived through the vec stack with no wrapper in sight.

## Check yourself

1. F-23 makes every checkpoint a triplet. What exactly breaks if you deploy
   `model.zip` without its `vecnormalize.pkl`, and why is that failure dangerous in a
   way a crash is not?

2. F-21 says no stage ever advances on step count alone. Point to three places in the
   code where that rule is structural rather than procedural.

3. Stage B could have evaluated "agent and baseline, same 200 seeds". Why is that
   comparison unfair, what does the harness do instead, and why is the stored baseline
   result a twin roll rather than the live recording?

4. Defend this design choice: PPO trains with gamma 0.997 while the reward's shaping
   gamma is 1.0, which breaks exact policy invariance. Why is the mismatch acceptable,
   and what would you show an examiner who pressed?

5. The solo env charges pit time to the pace reward term; the full env deliberately
   does not. Defend both, or explain why this is not an inconsistency.

---

### Answers

1. The network was trained on z-scored observations; without the statistics it
   receives raw values on completely different scales, and every prediction is
   computed from garbage. Nothing raises — the model plays confidently and badly,
   which is worse than a crash because nothing tells you to look. The triplet ships
   the statistics with the weights, hashes both into the manifest, and
   `test_checkpoint_roundtrip` proves save-then-load reproduces the exact action.

2. First, the gate functions in `gates.py` take no budget or step-count parameter, so
   a step-based pass cannot be expressed. Second, `curriculum_gates.json` records
   `budget_stop` and `transition` as separate fields, so a ceiling exit can never be
   read as a pass. Third, the loop's early stage exit happens
   only through `GateEvalCallback` returning `False` on a passed decision — the
   ceiling merely bounds `learn()`, and `test_no_stage_ever_advances_on_step_count_alone`
   pins the whole arrangement.

3. Same seed is not same race: the RNG stream is consumed at a policy-dependent rate,
   so the two runs' events diverge at the first different decision and every
   difference after that is luck, not skill (the F06 twin lesson). Instead the
   heuristic's races are recorded once as EventTraces and the agent replays each
   frozen twin — identical events by construction (A-06). The baseline's stored
   result is its own twin roll so both sides face the same deterministic physics
   (noise zeroed, mean pit service); pairing a noisy live run against a deterministic
   replay would bias every pair, and the self-pair-is-a-tie test would catch it.

4. The value function's target over a 70-lap horizon needs discounting to control
   variance, and 5.6.1's 0.997 keeps lap 1 at 81% weight at the flag — the master
   spec wins (F07 decision 2). The cost is that the potential-based shaping telescopes
   only approximately: the per-lap residual is (1 − 0.997) × 0.1 × position — around
   three thousandths of a unit, against a pace term whose one-sigma lap is 0.02 and a
   P1 terminal of 10.0. Pressed, I would show
   the `training.yaml` comment quantifying the residual, and the F08 gamma-1.0
   sensitivity run demonstrating the headline result does not depend on the mismatch.

5. In the full env a pit stop is already priced twice over — you lose places (position
   term) and finishing points (terminal) — so charging pit time to the pace term as
   well would double-count it; 5.5.4 excludes it deliberately. Solo, both of those
   channels are constants: position is always P1 and the terminal is fixed, so a pace
   term fed racing time only would make stops literally free and Stage A would
   optimise into pit-happy nonsense. Including pit loss in the solo pace term restores
   the price through the only channel that still carries signal, and it matches what
   the Stage A reference charges per stop — the gate stays like for like. Not an
   inconsistency: the same total cost, routed through whichever terms are alive.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| PPO / MaskablePPO (5.6.1, F-16) | F07 | Clipped policy-gradient RL — collect rollouts, advantage-weighted nudge, clipped per batch — with action masks applied inside the distribution; sb3-contrib fetches `action_masks()` through the vec stack, so no wrapper is needed. |
| VecNormalize observation statistics (5.6.1) | F07 | A vec-env wrapper keeping running mean/variance per obs slot and feeding the net z-scores; obs only, never the hand-scaled reward — and the statistics are learned state the model is meaningless without. |
| Checkpoint triplet (F-23) | F07 | Weights + vecnormalize.pkl + manifest saved atomically as one unit, both artifacts sha256-stamped into the manifest, so a served model can prove which statistics it was frozen with — the guard against the silent wrong-inputs deployment bug. |
| Gate decisions as pure functions, budgets as ceilings (F-21, R-12) | F07 | Stage advancement decided by pure functions of eval histories (plateau best-of-window, one-sided time bar, paired finish-ahead, stagnation clock) whose signatures have no budget input; a ceiling hit logs `budget_stop`, never a transition. |
| Matched-gamma telescoping and the conscious mismatch (F-15, 5.5.4) | F07 | Potential-based shaping is exactly policy-invariant only when the training gamma equals the shaping gamma; SENNA trains at 0.997 against shaping gamma 1.0 as a documented choice with a quantified ~0.0003/lap residual and matched-gamma F08 ablations. |
