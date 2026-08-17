# The three screens, explained for anyone

This is the walkthrough document. It covers what is on each screen, what every
control does, and what each number means — in plain English, assuming you know
nothing about the project. Its companion, `presentation-02-what-happens-underneath.md`,
explains how the thing actually works.

Written for a video presentation, so each screen ends with a short **On camera**
block: what to click, in what order, and what to say while you do it.

---

## First, the one-paragraph version

SENNA is a Formula 1 race-strategy engine. It has a simulator that races 22 cars
around a circuit under the 2026 regulations, and a computer player — trained by
reinforcement learning — sitting in one of those 22 cars. Every lap, that player
makes two choices: whether to pit (and for which tyre), and how to spend its
electrical energy. The three screens let you set up a race, watch it back, and
ask the player why it did what it did.

The important thing to say early, because it shapes everything: **the agent has
no plan.** It never sits down before the race and writes "stop on lap 18". It
makes one decision, on one lap, with the information available on that lap, and
then does it again 56 more times. Every screen is built to respect that.

---

## Screen 1 — Race

This is the home page. It does two jobs: set a race up, and report what happened.

### The sidebar: setting the race up

**Circuit.** A dropdown. Not every circuit is in it — only the ones where the
project managed to fit a real tyre-wear curve from data. Three of them carry a
label after the name:

| Circuit | Label | Why it's labelled |
|---|---|---|
| Chinese Grand Prix | balanced | A normal mix of corner types |
| Australian Grand Prix | flowing | Fast, few heavy braking zones |
| Monaco Grand Prix | street | Slow, tight, almost impossible to overtake |

These three are the "archetypes" the evaluation reports on separately, because
they stress strategy in different ways. They were picked because their tyre
curves were measured at that circuit rather than borrowed from a similar one.

**Race laps** and **Harvest cap.** Two read-outs that update when you change
circuit. Race laps is self-explanatory. Harvest cap is how much electrical
energy the car is allowed to recover per lap, in megajoules — this is a real
2026 rule, and it differs circuit to circuit because a track with more heavy
braking gives you more to recover.

**The tyre-model caption.** Small grey text under those two numbers. It either
says all three compounds were fitted at this circuit, or names the ones borrowed
from elsewhere. This is the project being honest about where its numbers came
from, on the screen, at the moment you choose. Worth pointing at in the video.

**Conditions.** Dry, mixed, or wet risk. Dry means slick tyres all race. The
other two turn on a weather model that can change the track under you.

**Era.** 2026 or 2024. This swaps the physics — engine rules, tyre behaviour,
energy limits — between the new regulations and the old ones. It exists so the
agent can be compared against real 2024 races on the same terms.

**Rival band.** Test or train. The other 21 cars run scripted strategies fitted
to historical data. Those scripts are split into two groups: one the agent saw
while learning, one it never saw. "Test" is the group it never saw, which is the
honest setting, and the caption on screen says exactly that.

**Starting position.** Where your car lines up, P1 to P22. Defaults to P8, mid
grid, because starting at the front or the back makes the strategy question
boring.

**Seed.** A number that fixes the randomness. Same seed plus same settings means
the identical race, every time — same weather, same safety cars, same tyre
failures. Leave it blank and the server picks one and tells you what it picked.
This is what makes any result in the project reproducible.

**Run race.** Press it and a spinner appears saying the agent decides every lap,
so this takes a moment. It takes roughly eighteen seconds for a full grand prix.
Nothing is faked during that wait; the race is genuinely being run.

### The main area: what happened

Before you run anything, you get a title card and a warning worth reading out
loud in the video: nothing here is a prediction about a real grand prix, the
simulator is calibrated from 2022–25 telemetry and transformed to 2026 rules,
and its agreement with reality is measured and reported — and does not meet the
bar the project set for it. The project says this on its own front page rather
than burying it.

After the race, six numbers across the top:

- **Grid** — where you started.
- **Finish** — where you ended, or DNF if the car retired.
- **Stints** — how many separate sets of tyres were used.
- **Stops** — pit stops, always one fewer than stints.
- **Race laps** — the length of the race.
- **Race time** — total, as hours:minutes:seconds.

Points are deliberately not shown. Internally the agent's scoring divides the
real points table by 2.5, so a second place would display as 7.2, which looks
like a bug. Rather than convert it back and risk implying the agent optimises
FIA points directly, the screen just doesn't show it.

**The stint bar.** One horizontal bar, split into coloured blocks — one block
per set of tyres, width proportional to how many laps it lasted. Hovering gives
you the compound and the lap range. The colours are the project's own invention,
not any tyre supplier's branding.

**The race story.** The main chart: position against lap, for all 22 cars. The
faint grey lines are the rivals. The bright line is the agent. Dashed vertical
lines mark the laps where the agent pitted. The y-axis is upside down on purpose
so that first place is at the top, which is how everyone reads a race.

This chart is the single best thing to narrate on camera. You can see the agent
drop several places at a pit stop, then climb back as the cars that stopped later
come in.

**Pit stop schedule.** A small table: stop number, tyre it came off, tyre it went
on, and the lap. Four columns, and only four. There is no "how long the stop took"
column, because the simulator folds pit time into the lap time and never reports
it separately — so a service-time column would be a made-up number.

**Classification.** The finishing order at the final lap: position, car, tyre,
tyre age. Cars are C01 to C22; they are not named after real drivers.

**The note at the bottom.** Every screen has one of these grey notes, and they
all state what the screen is *not*. This one says the stints were read back from
what the race actually stored, that no plan preceded the race, that pit service
time isn't shown because it isn't served, and that the rivals are scripted
strategies rather than 21 more learned agents. That last point matters and people
will ask about it.

### On camera

Pick Chinese Grand Prix, dry, 2026, test band, P8, seed 55. Say: "I'm going to
start eighth, in the dry, against the rivals the agent has never trained
against." Press Run. While it thinks, say what it's doing — 57 laps, one decision
per lap. When it lands, go straight to the race-story chart, trace the bright
line with the cursor, and point at the dashed lines: "that's a pit stop, that's
what it costs, and that's it earning the places back."

---

## Screen 2 — Playback

The Race page shows you the finished race as one picture. Playback walks through
it a lap at a time.

You need a race first. Open this page without running one and it tells you so.

**Play / Pause, Restart, and the lap slider.** Play advances one lap roughly
every third of a second. Drag the slider yourself and it pauses, so scrubbing
never fights the autoplay.

**Five read-outs across the top**, all for the agent's car at the current lap:

- **Lap** — where you are, out of the total.
- **Position** — the agent's place at the end of this lap.
- **Tyre** — compound, and how many laps that set has done.
- **Battery** — energy stored, in megajoules. Watch this number: it drains when
  the agent deploys and refills under braking. Under the 2026 rules the usable
  store is 4 MJ, so anything you see lives in that window.
- **Stops so far** — pit stops up to this lap, not the whole race.

**Event banner.** If a safety car, virtual safety car or red flag started on this
lap, a warning strip appears. These are the moments that decide races, and they
are the moments the agent has to react to without knowing they were coming.

**The left chart.** Position against lap again — but only up to where the
playhead is. It never draws the future. That's a deliberate choice: the chart
should show what was knowable at that moment, not the answer.

**The right table.** The live order at this lap: position, car (the agent marked
with a small arrow), gap to the car ahead in seconds, tyre, tyre age, and an
"IN" flag if that car is in the pits this lap.

**The note.** Says two things. The simulator works in whole laps, so there is no
within-lap ordering to show and none is invented. And scrubbing or playing only
reads stored data — nothing is being re-simulated as you drag. The race finished
before the page opened.

### On camera

Press Play and let it run. Talk over it. When the battery number moves, say what
it means. When a car shows IN, point out the position table re-sorting the lap
after. If your run had a safety car, scrub back to it and stop there — that's the
most interesting single lap in any race, and it sets up Screen 3 perfectly.

---

## Screen 3 — Explainability

This is the screen the whole project is built around. Pick any single lap of the
race and ask: why that call?

At the top, a slider over every lap that has a stored explanation. Under it, two
lines:

- **The decision.** Something like `Lap 17 - pit for Medium, run balanced
  (probability 0.87)`. What it chose, on both of its two choices, and how
  confident it was.
- **The plain-language line.** One sentence, like "Grip left was the strongest
  push toward this call." This sentence is assembled from a fixed template — no
  text generation is involved, so the card can never say more than the numbers
  support.

Then three sections, in a deliberate order, strongest evidence first.

### Section 1 — Reward decomposition (primary)

A bar chart with three bars, and a total underneath.

Reinforcement learning works by giving the agent a score for its behaviour, and
this shows exactly what score this lap earned, broken into its parts:

- **Pace shaping** — was this lap quick, relative to a reference lap for this
  circuit?
- **Position (potential-based)** — did it gain or lose track position? "Potential
  based" is a technical trick: it's built so that gaining a place and then losing
  it again nets out to exactly zero, which stops the agent farming the score by
  yo-yoing.
- **Terminal points** — the real 2026 championship points for where it finished,
  and zero on every lap except the last.

The note under it makes the point that matters: there are three terms and only
three, and being legal is not one of them. The agent gets no reward for obeying
the rules and no penalty for breaking them. It can't break them — which is
Section 2.

This section is the strongest evidence on the page because it isn't a model of
anything. These are the actual numbers the simulator handed the agent.

### Section 2 — Alternatives the policy weighed (secondary)

Two tables side by side, one for each decision the agent makes.

**Pit head**, six options: stay out, or pit for Soft, Medium, Hard, Intermediate,
or Wet. **Energy mode head**, four options: conserve, balanced, attack, defend.

Each row shows the option, the probability the agent gave it, and whether it was
legal. A small arrow marks the one it picked. Rows are sorted most-likely first.

The "Legal: no" rows are the interesting ones. Those options were removed before
the agent ever saw them — it did not consider fitting a slick tyre in the wet and
reject it; it was never offered. That's what "masked" means where the probability
should be. This is how the project gets 100% rule compliance without ever
penalising the agent for breaking rules.

**"What would have changed it."** Underneath, on pit laps, a few lines like "this
call flips if tyre age reaches 24 laps". These are found by taking the real
situation, changing one thing at a time, and re-asking the actual trained network
what it would do. Genuine counterfactuals against the real agent, not a guess.

### Section 3 — Feature attribution, SHAP (exploratory, collapsed)

This section is folded shut by default, and that is a decision, not an oversight.

SHAP is a standard technique for asking "which inputs pushed this prediction
which way". The complication: SHAP doesn't work cleanly on the kind of neural
network the agent is. So the project trains a second, simpler model — a decision
tree ensemble — to imitate the agent, runs SHAP on that, and shows you the result.

Which means the bars are explaining the imitator, not the agent. The project's
response is to measure how often the imitator agrees with the real agent and
print that number right there: **99.7% agreement on pit calls, 99.1% on energy
calls.** If that agreement ever dropped below 90%, the pipeline refuses to
produce cards at all.

Green bars pushed toward the decision, red bars pushed against it. The features
are given readable names — "grip left", "gap to the car ahead", "battery charge"
— rather than raw variable names.

The honesty line at the bottom spells the caveat out: attribution via a
99.7%-faithful surrogate, and not a causal claim.

### On camera

This is your closing act, so slow down. Land on a pit lap. Read the decision line
out. Then work down the three sections and say why they're in that order:
"These first numbers are what actually happened. These second numbers are what
the agent itself was thinking. This third section is a helpful approximation, and
it's last, and it's closed, because it's the only part that isn't the agent
itself." Then open it anyway and point at the 99.7%.

If you say one sentence about the whole project on camera, say that one.

---

## The vocabulary, in one table

Anything a non-specialist might trip over.

| Term | What it means here |
|---|---|
| Agent | The computer player that makes the strategy calls |
| Reinforcement learning | Training by trial and error against a score, over many thousands of races |
| Policy | The trained network itself — situation in, choice out |
| Head | One of the two decisions it makes each lap (pit, energy mode) |
| Mask | The filter that deletes illegal options before the agent chooses |
| Compound | Tyre type — Soft, Medium, Hard, Intermediate, Wet |
| Stint | One continuous run on a single set of tyres |
| Degradation | How much slower a tyre gets as it ages |
| SOC | State of charge — how full the battery is, in megajoules |
| Harvest | Recovering energy under braking |
| Deploy | Spending stored energy for extra power |
| MGU-K | The motor that does both, rated at 350 kW under 2026 rules |
| Manual Override | The 2026 overtaking aid: extra power when within 1 second of the car ahead |
| Safety car / VSC | Neutralisations that slow the whole field and shuffle strategy |
| Seed | The number that makes a random race reproducible |
| Frame | One stored snapshot of all 22 cars at the end of one lap |
| Card | One stored explanation of one decision on one lap |
| Surrogate | The simpler stand-in model that SHAP is actually run on |
| Fidelity | How often the surrogate agrees with the real agent |

---

## Three questions you will get asked

**"Is it playing against other AIs?"** No. The other 21 cars follow scripted
strategies fitted to real historical race data. It's one learner against a field
of realistic opponents, not a tournament of agents.

**"Could this be used at a real race?"** No, and the project says so on its own
front page. The simulator's agreement with reality is measured, reported, and
fails the bar that was set for it in advance. It's a research system about
strategy under a new rulebook, not a race-day tool.

**"How do you know it isn't just making the explanations up?"** Because of the
order of the three sections. The first two are the real numbers from the
simulator and the real probabilities from the network. Only the third is an
approximation, and it carries its own measured accuracy on screen.
