# What happens underneath the three screens

The companion to `presentation-01-the-three-screens.md`. That one covers what you
see; this one covers what runs. Still plain English, but it goes deeper — enough
to answer the questions an examiner asks after the demo ends.

---

## The shape of the whole thing

Four pieces, and they only talk in one direction.

```
   your browser
        |
        v
   [ Streamlit ]      the three screens. Draws charts. Owns no simulation.
        |             Every number on screen arrived in an HTTP response.
        v
   [ FastAPI  ]       the door. Validates requests, runs races, serves stored results.
        |
        v
   [ simulator + frozen agent ]   the research code: 22 cars, the trained network,
        |                          the explanation pipeline
        v
   [ PostgreSQL ]     races, per-lap snapshots, decision cards
```

The rule that keeps this honest is the one at the top: the interface computes
nothing. If a number appears on a screen, there is a request that carried it and
a row in the database behind it. You cannot get a figure onto a SENNA screen by
calculating it in the front end, because the front end has nothing to calculate
with.

The layer that used to sit here — a job queue, a background worker, a 3D
renderer — was removed for the dissertation build. A race now runs inside the
request that asks for it. That costs eighteen seconds of waiting and saves two
services, which for a system that has to be reproducible by someone else is a
good trade.

---

## Those eighteen seconds, step by step

You press **Run race**. Here is the whole chain.

1. **Streamlit posts the settings** to the API: circuit, grid slot, seed, era,
   weather, rival band.
2. **The API validates them.** Grid position must be 1–22. An unknown circuit is
   refused with a message telling you to list the library. If you left the seed
   blank, one is drawn now and recorded, so the race stays reproducible.
3. **A row is written** to `simulation_runs` with status `running`, before
   anything is simulated. If the race dies halfway, that row is marked failed
   rather than silently vanishing.
4. **The race runs on a worker thread.** Not on the main event loop — the API has
   to keep answering other requests while a race is in progress.
5. **The frozen agent is loaded**: three files together. The trained network
   weights, the input-normalisation statistics it was trained with, and the
   surrogate models used for explanations. All three are baked into the image.
6. **The race runs lap by lap.** For each lap the code stores two things: a
   **frame** (all 22 cars — position, gap, tyre, tyre age, plus the agent's
   battery and reward) and a **decision card** (what the agent chose, what else
   it could have chosen, and why).
7. **Everything is saved in one transaction.** Either the whole race lands in the
   database or none of it does. A half-stored race would draw a chart that looked
   fine and was wrong.
8. **The API returns the run id.** Streamlit then reads the results back with
   ordinary GET requests — the same requests anyone else could make.

Nothing in that list is a mock. The eighteen seconds is real work.

---

## Inside the simulator: what one lap is

The simulator is **lap-level**, not continuous. It does not model a car through a
corner. It models what a lap *did* to a car: how much time it took, how much tyre
was consumed, how much energy went in and out. That's the right resolution for
strategy, and it's why 22 cars over 57 laps runs in seconds instead of hours.

Each lap happens in two halves, and the gap between them matters.

**First half — the track resolves.** Did a safety car come out? Did it start
raining? Is the pit lane open? This has to happen first, because the rival cars
need to know the state of the track before they can decide anything. A safety car
is exactly when a strategist changes their plan.

**Then every car commits to its decision** — the agent through its trained
network, the 21 rivals through their scripted strategies.

**Second half — the lap is run.** Lap times are computed from fitted physics: a
base pace for that circuit, plus the penalty for tyre wear, plus fuel weight,
minus whatever energy was deployed, plus random variation. Pit stops are served.
Tyres age. Positions are recalculated from cumulative race time. Occasionally a
tyre fails.

The randomness is deliberately structured. Six things draw random numbers each
lap, always in the same order: track status, weather, rival pit choices, tyre
failure, pace noise, pit service. Fix the seed and every one of those draws is
identical, which is what makes a race reproducible. Reorder them and every seeded
race in the project silently changes — so there are tests whose only job is to
catch that.

The 21 rivals are worth being precise about, because it's the most common
misunderstanding. They are **not** other learned agents. They run strategies
fitted to real historical races — realistic pit windows, realistic compound
choices, realistic reactions to safety cars. One learner against a field of
plausible opponents.

---

## Inside the agent: how a decision gets made

### What it sees

Every lap, the agent receives **32 numbers**. That's its entire view of the world.
Each one is scaled to sit between -1 and 1, and each is named and justified:

- Where it is in the race, its position, places gained since the start
- Which tyre it's on, how old it is, how much grip is estimated to be left,
  whether that tyre is cold, in its window, or past its cliff
- How many stops it has made, whether the mandatory second compound has been used
- Fuel remaining, battery charge, energy recovered and spent last lap
- Gaps to the cars ahead and behind, and how their tyres compare to its own
- Whether it's within the 1-second window for the overtaking aid
- Green flag / virtual safety car / safety car, pit lane open, dry / damp / wet,
  how wet, track temperature

That's it. No view of anyone's strategy, no race history beyond what's baked into
those numbers — tyre age, stops made, and how much energy went in and out on the
previous lap are the only backward-looking inputs it has. It sees this lap's
situation and answers.

### What it chooses

Two decisions at once, which is why the code calls them two **heads**:

- **Pit head**, six options: stay out, or pit for Soft, Medium, Hard,
  Intermediate, Wet.
- **Energy mode head**, four options: conserve, balanced, attack, defend.

### What it is not allowed to choose

Before the network picks anything, a **mask** deletes the illegal options. Each
deletion carries a reason, and those reasons are what the Explainability screen
prints:

| Reason | What it means |
|---|---|
| pit lane closed | You cannot pit under this track status |
| slick above wet threshold | Too wet for a dry tyre |
| inter outside damp band | Intermediates only make sense in a narrow wetness range |
| wet requires wet track | Full wets on a dry track are not an option |
| two compound rule | Last lap of a dry race and you still haven't used a second compound — staying out is now illegal |
| SOC below attack floor | Not enough battery to run attack mode |
| compound unfitted for circuit | No measured tyre curve here, so this tyre would behave unrealistically |

Note what that last one is: not a sporting rule, but a data limit. A compound
with no fitted wear curve would read as never wearing out, and the agent would
learn to exploit a modelling gap. So it's removed and labelled as a data
restriction rather than quietly allowed.

**This is the design decision worth defending in a viva.** The obvious way to
teach an agent the rules is to punish it for breaking them. This project refuses
that, because a punished agent has learned a trade-off — it will break the rule
whenever the payoff exceeds the fine. A masked agent cannot express the illegal
action at all. The measured result: across 480 evaluation races, zero illegal
actions and zero actions that had to be corrected. Not because it learned well,
but because the option never existed.

Continuous limits are handled the same way, one layer down: energy that would
take the battery outside its 4 MJ window is clipped by the physics, not
discouraged by the score.

### What it is trying to achieve

The score has exactly three parts, and the project is strict that nothing else
gets added:

- **Pace shaping.** How fast this lap was against a reference for the circuit,
  divided by that circuit's own lap-time variability so the term means the same
  thing at Monaco and Monza. Deliberately small — an order of magnitude below the
  terminal term, so it nudges rather than competes with it.
- **Position shaping.** Built as a *potential* — the score depends on a function
  of position rather than the change directly, which mathematically guarantees
  that any sequence of moves returning to the same position sums to zero. It
  encourages progress without letting the agent farm points by losing and
  regaining a place.
- **Terminal points.** The real 2026 championship table (25, 18, 15, 12, 10, 8,
  6, 4, 2, 1) divided by 2.5, so a win is worth 10. Paid once, at the end. A
  retirement pays zero rather than a negative — retiring already forfeits
  everything, and stacking a penalty on top would double-count the risk.

There is no fastest-lap bonus, because that point was abolished from 2025. There
is no legality term, for the reason above. Three terms, and you can see all three
on screen for any lap you like.

---

## How it learned

Training happened in three stages, each unlocking more of the problem. A stage
ends when the agent stops improving *and* passes a competence test — never on
step count alone.

| Stage | World | Gate to pass |
|---|---|---|
| **A** — fundamentals | Alone at Monza, dry, no incidents | Improvement flattens off, and race time within 1.5% of a near-optimal scripted reference |
| **B** — competition | 6 circuits, 21 rivals, dry, safety cars on | Beats a rule-based strategy on at least 55% of 200 paired races, with a median position gain of at least zero |
| **C** — the full problem | 24 circuits, weather, red flags, everything | The final model |

"Paired races" in Stage B means the agent and the baseline face identical random
draws — same weather, same safety cars, same tyre failures. Any difference
between them is strategy, never luck. That pairing idea runs through the whole
evaluation.

The whole curriculum was then run three times from three different random seeds,
and the best of the three was picked on validation races it hadn't been scored on
during training. That winner was **frozen**: weights, normalisation statistics
and configuration hashed and stamped with a version string. The API refuses to
start if it's asked for a version it doesn't have, rather than quietly falling
back to a different model.

Training code never runs in the serving stack. The model you demo cannot learn
from your demo.

---

## Where the three explanations come from

The Explainability screen shows three things in a fixed order. They are ordered
by how directly they come from the agent, and it's worth being able to say why.

**Reward decomposition — recorded, not modelled.** These numbers were produced by
the simulator as the race ran and written straight into the lap's frame. Nothing
interprets them. This is the most trustworthy panel on the page and it is
therefore first.

**Alternatives the policy weighed — the network's own output.** When the agent
chooses, it doesn't emit one answer; it emits a probability over every legal
option. Those probabilities are stored exactly as the network produced them,
after masking. So "87% pit for Medium, 9% stay out" is what the trained network
actually believed. Also not modelled — but it's a snapshot of one lap, not a
strategy search, and the note on screen says so.

**"What would have changed it" — real counterfactuals.** The code takes the
recorded situation, sweeps one input across its plausible range, and asks the
**real network** what it would have done at each point. Two details keep this
honest. The mask is rebuilt at every step of the sweep, so it can never report a
flip onto an action that would have been illegal there. And the sweep walks
outward from the value the decision actually had, so what gets reported is the
*nearest* thing that would have changed the call, not the first one found
scanning from zero.

**SHAP — the approximation, and the only one.** Here's the honest problem: SHAP
is designed for models like decision trees, and it doesn't transfer cleanly to a
policy network. So the project trains a stand-in — an XGBoost model, one per head
— to imitate the agent's outputs, and runs SHAP on the stand-in.

Everything about how that's presented follows from the fact that it's a stand-in:

- Agreement with the real agent is **measured**, not assumed: 99.7% on pit calls,
  99.1% on energy calls, on decisions held out from the imitator's training.
- There's a **hard gate at 90%**. Below it the pipeline refuses to produce any
  cards at all — the code raises rather than shipping explanations it can't
  stand behind.
- If the stand-in was fitted to a different version of the agent, the card
  builder **refuses outright**. The version is read back off disk rather than
  passed around in memory, so a stale artifact is caught rather than trusted.
- On screen it is third, collapsed, and captioned with its own accuracy and the
  words "not a causal claim".

That ordering is the thesis of the interpretability work in miniature: say where
each explanation came from, and rank them by how close to the truth they are.

---

## Why the numbers are checkable

A few practices that are easy to state on camera and hard to argue with.

**Every constant lives in a config file with its origin written next to it.**
There are no numbers typed into the code. Each one is labelled as *sourced* (with
the document it came from), *fitted* (with the notebook that produced it),
*stylised* (an admitted visual choice), or *operational* (an engineering default
with its reasoning). An inline constant is treated as a defect.

**The physics is corrected from primary sources.** The 2026 rules are widely
misreported, and the project's own earlier specification had them wrong. The
electric motor is 350 kW, not 400 — that's the engine. The energy store is a 4 MJ
window, not 8 MJ. There is no per-lap deployment cap in the rulebook; the era is
limited by how much you can recover, and that cap varies by circuit. The audit
trail of those corrections is in the repository.

**Results regenerate from stored evidence.** `make report` rebuilds the entire
evaluation chapter from committed data — no model, no database, no GPU required.
Anyone with a clean copy can re-derive every table.

**Seeds are frozen and published.** The races the evaluation is scored on are
listed in a manifest. Every result row carries the configuration hash and model
version that produced it.

**Robustness is tested rather than assumed.** When the FIA tightened the harvest
cap from 8 to 7 MJ, the frozen agent was re-run under the tighter cap instead of
being quietly retrained. It loses 0.13 places and runs out of energy twice as
often. That's reported.

---

## What it actually achieved

Eleven measures, with their targets set *before* the runs that scored them. Two
met, six missed, three report-only. Present it that way — a project where every
metric passes is a project whose bars were set afterwards.

| Measure | Result | Reading |
|---|---|---|
| Position gain vs engineered baseline | **+2.28 places** (CI 1.91–2.66) | Met. The headline: it genuinely beats a competent rule-based strategist. |
| Regulatory legality | **0 illegal, 0 corrected** in 480 races | Met — and by construction, then measured anyway. |
| Tyre failures | 37.9 per 100 races, target under 2 | Missed, and it explains the headline: the agent buys track position by over-running its tyres. |
| Vs real 2024 strategies | 1 win, 8 losses, 1 tie (p = 0.039) | Missed, significantly. Against replayed real strategies it loses reliably. |
| Energy utilisation | 0.704 of the deployable budget | Missed — though the 0.90 bar is unreachable at several circuits, which the write-up says out loud. |
| Safety-car decisions | SC precision 0.82, recall 0.40 | Missed, but it now reacts to virtual safety cars at all — ten calls, none wrong. |
| Sim-to-real agreement | 0 of 5 circuits within the bar | Missed. The validation split forbids refitting to fix it. |
| Luck share | **78.6%** of finishing-position variance | The interesting finding: most of a race result is the draw, quantified. |

The tyre-failure row is the one to dwell on, because it's the most intellectually
honest moment in the project. The agent wins places, and it wins them partly by
doing something a real team would not accept. The evaluation found that, named
it, and connected it to the headline result rather than reporting the good number
alone.

---

## Answers to the harder questions

**"Why reinforcement learning rather than an optimiser?"** Because the problem is
sequential and uncertain. A classical optimiser can compute a good stop lap if
you tell it the future. Here the future includes safety cars, weather and 21
opponents reacting to you. The agent has to choose without knowing, one lap at a
time — which is exactly the situation on a real pit wall.

**"Isn't the agent just overfitting to your simulator?"** Partly, yes, and the
project states it: the agent optimised the simulator it is scored in, while real
teams optimised reality. The sim-to-real measure is reported and it fails. That's
why the counterfactual comparison against real 2024 strategies is in there — and
why it's reported as a loss.

**"How can you claim 100% rule compliance?"** Because it isn't a claim about
learning. Illegal actions are removed before the network chooses, and continuous
limits are clipped by the physics. Compliance is structural. It was then measured
across 480 races anyway, and came back at zero violations.

**"Why should I trust the explanations?"** Two of the three panels aren't
explanations at all — they're recordings of what happened and what the network
output. Only SHAP is an approximation, it's ranked last, and it carries its
measured agreement with the real agent on screen.

**"What would you do next?"** Fix the tyre-failure behaviour, because it's the
defect that most undermines the headline result. The agent found that over-running
tyres pays inside this simulator, which means the simulator makes it too cheap.

---

## The thirty-second version, for the end of the video

A simulator races 22 cars under corrected 2026 rules. A reinforcement-learning
agent drives one of them, deciding pit stops and energy use one lap at a time,
with illegal options removed before it ever chooses. It beats an engineered
baseline by 2.28 places, and it does so partly by abusing its tyres, which the
evaluation caught and reported. Every constant carries its source, every result
regenerates from stored evidence, and every decision comes with an explanation
that says how much it can be trusted.
