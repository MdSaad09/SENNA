# F23 — three tabs, one palette, and a test that proved nothing

## What we built and why

Before this feature the dashboard was six routes wearing whatever Tailwind grey the
author reached for that day: 19 distinct neutral utilities across about 174 call sites,
plus a second and larger colour surface nobody owned at all — inline hexes in the recharts
and R3F code, to the point where `SocBar` imported `SOC_TINT` out of `SocPanel` to keep two
blues in step. It worked. It did not read as one instrument.

F23 folds the six routes into three tabs (STRATEGY, CIRCUIT, ANALYSIS) with a section rail
underneath, puts every colour in one file, and adds the two surfaces the dashboard was
missing: a Strategy page that says what the agent actually did with its tyres, and a
Decisions section that shows the reward decomposition and the alternatives the policy
weighed. The circuit camera now fits itself to whichever ribbon is loaded, so Monaco and
Spa both fill the panel.

The six spec views did not go anywhere. 5.10.2 fixes them and they survive as sections —
and the reason they became sections on a rail rather than one long scrolling page is
5.10.3: only one canvas may be mounted at a time, and a scroll layout would co-mount the
circuit and the replay canvases the moment the boundary between them crossed the viewport.
The tab shell is a consequence of a physics-of-the-browser constraint, not a taste call.

Three things in this feature are worth your revision time, and none of them are the
tabs. Saad's reference screenshots were beautiful and their content model was wrong in
four places. A property test ran 500 seeded races over the stint derivation and could not
have caught the bug that was in it. And a colour sampled faithfully from the reference
turned out to be illegible on exactly the text that carries the project's honesty
statements.

## New ideas in this feature

**A reference is an aesthetic baseline, not a content model.** Saad supplied three
screenshots on 11 August and the instruction was "match or beat". They are genuinely good:
dense, monospaced, dark, hairline-ruled. They also contain DRS twice (a parameter card
reading "DRS 1 zones" and a legend line), a starting-position slider running P1 to P20, a
reward panel decomposed into six invented headings — Tire Degradation Management, Fuel Load
Optimisation, Weather Adaptation and friends — and an "Optimal Strategy 89.0/100" score
produced by a planner that does not exist.

The discipline is to take the *grammar* of a reference and refuse its *claims*. There is no
DRS in 2026; the overtaking aid is Manual Override and the circuit annotation is X-mode
sections. The grid is 22 and `SimulationCreate.grid_position` has been bounded `ge=1, le=22`
since F10. The reward has exactly three terms. And SENNA has no planner: the agent decides
lap by lap inside the simulator, so a score computed before the race is a screenshot of a
different product.

What makes this more than a moral is that every replacement is better than the thing it
replaced. Six invented reward terms became the three real ones, read out of the frame the
env actually served. A ranked beam search became the card's own masked action
probabilities, so the "alternatives" are the options the policy really weighed, with the
illegal ones struck through and labelled with the rule that forbade them. The viva version:
**the reference was adopted as a visual language and rejected as a data model, because
copying a fabricated panel into a dissertation about interpretability is the one defect the
project cannot survive; in all four cases the honest replacement was already available in a
payload the API was serving.**

**Two signals that look the same and are not.** There is no served stint list, so the
Strategy page derives one from the frames. The obvious signal is the compound: a stint is
the run of laps between compound changes. That is what shipped first, and it is wrong.

Read `senna/env/engine.py:173-179`:

```python
def _apply_pits(state, pit, failed, red_flag: bool) -> None:
    changed = pit != STAY_OUT
    state.compound = np.where(changed, pit, state.compound)
    stopped = changed | failed | red_flag
    new_compound = state.compound != state.first_compound
    state.second_compound_used |= stopped & new_compound
    state.pit_count += (changed | failed).astype(int)
```

Two ways for a real stop to leave the compound untouched. A stop onto the compound already
fitted: `changed` is true, so `pit_count` increments, but `np.where` writes back the value
the car already held — and nothing in `masks.py` forbids re-fitting the current compound.
And a tyre failure: `changed` is false, `failed` is true, the compound is untouched, and
`pit_count` still increments. Both stops vanished from the timeline, and the headline read
one stop fewer than the race contained.

The authoritative signal was one line away. `senna/serve/frames.py:55` computes
`in_pit = pit_count > prev.pit_count`, which is exactly the quantity that increments in
both cases. The general shape: **when two fields move together most of the time, find out
which one the writer actually writes and read that one.** Compound change is a
*consequence* of a pit stop, and consequences have exceptions.

**A property test only tests what its generator can produce.** You met seeded property
loops in F11: a mulberry32 generator, a plain loop, the seed printed in every assertion.
`stints.test.ts` runs 500 of them. It was green against the broken code, and it could not
have been anything else, for two independent reasons.

The generator changed the compound on every stop it produced. The two cases that break the
old logic were outside its support, so no seed could ever reach them. And the assertion
only ran one direction — every stint boundary is a pit lap — which the broken code
satisfies trivially, since a compound change without a stop is a state the server cannot
produce. The direction that bites is the converse: every pit lap opens a stint. Nobody
wrote it.

This is the sharpest version of F14's break-it-on-purpose rule the project has produced, and
it is worth stating as a habit rather than an anecdote: **for a property test, ask two
questions before you trust it — can the generator produce the failing input, and does the
assertion run in the direction the bug travels?** Both fixes are three lines. The generator
now re-fits the same compound one stop in seven, and the converse assertion is a `Set` of
boundaries checked against every `in_pit` frame.

**Writing to the URL behind the router's back.** Every view that POSTs a run writes the new
id into the URL so the link stays shareable. They all did it with
`window.history.replaceState`, which is the browser's own history API — it changes the
address bar and pushes an entry, and it tells nobody. React Router's data router keeps its
own `location` in React state, updated when *it* navigates. `useLocation().search` therefore
kept serving the query from before the run.

The address bar looked right, which is why this survived review by eye. But every consumer
of `useLocation` — the three tab links, the section rail, both 5.13 jump links — handed on a
URL with no `?run=`, so the demo's 1:15 beat would have opened the energy view's own run
picker instead of the SOC trajectory. Mental model: `history.replaceState` is writing on the
whiteboard; `setSearchParams` is telling the person who is keeping the minutes.

**Contrast is a correctness property here, not a taste one.** The palette was sampled from
the screenshots by decoding the PNGs and counting dominant colours, which is a genuinely
nice provenance story — `ground` is 41.3% of shot 3, `surface` 85.1% of shot 1. Two of the
sampled greys measured 3.96:1 and 2.79:1 against the ground. The 2.79 one was `ghost`, which
in this dashboard carries the R-07 footer and every 5.10.2 honesty statement at 11px.

The contrast ratio is `(L1 + 0.05) / (L2 + 0.05)` over WCAG relative luminance, and 4.5:1 is
the readable floor for small text. 2.79:1 survives neither a projector nor video
compression. So both tones were lifted — `faint` to `#8a99a6` (6.54:1), `ghost` to `#7d8994`
(5.35:1) — and the palette comment says why in full. **A disclaimer nobody can read is not a
disclaimer**, and "match the reference" stops at the point where matching it would make the
project's honesty claims invisible.

**Honesty statements, under test.** 5.10.2 gives every view a sentence stating what it is
not. Before F23 a restyle could delete any of them and the whole suite would stay green.
`honesty.test.tsx` pins all of them, and the two new sections' statements as well. It is the
most valuable file in the feature by a distance, which is the argument for it: the cost of
a missing test is not the bug you shipped, it is the class of change that becomes unsafe.

**Framing by the ribbon's own bounds.** The camera used to sit at a fixed `[0, 900, 900]` for every
circuit. Circuits run 3 to 7 km, so one distance can be right for exactly one of them, and
Monaco rendered at about half Spa's size. The fix solves for distance from the ribbon's own
bounds. Name-checked and not re-taught: the one-canvas rule and react-router (F11), the
jsdom WebGL boundary (F11), seeded property loops (F11), provenance comments (F00), stylised
provenance for visual data (F04), and E-15's empty-explanations state (F10, F13).

## The code, guided

Reading order: the language, the shell, the stint derivation, the two honest panels, the
camera, the guard.

### `frontend/src/config/palette.ts` — one place for colour

Block-level, because it is a table of constants; the interesting part is the comments. Every
export carries a `stylised` tag with its evidence, and `provenance.test.ts` now walks
`config/*.ts` and fails any `export const` that does not. That walk has a subtlety worth
copying: it scans *upward only* from the export to the first blank line. The first cut
scanned downward too, which meant a tag written below an export satisfied it — a constant
could be introduced by nothing at all and still pass.

The `CHART` block records a mistake being undone:

```ts
  // three separate readings that the first cut of this palette collapsed onto one grey:
  // the axis is furniture, the pit marks are data, and the divergence lap is the
  // counterfactual's headline moment
  pitMark: "#8a99a6",
  gridLine: "#1a242b",
  axis: "#637481",
```

Consolidating a palette is not the same as reducing the number of colours. Three things that
happened to be grey were not the same grey for the same reason, and merging them lost a
distinction the charts were making.

`tailwind.config.js` holds the same hexes a second time, under a `senna` namespace, because
importing a `.ts` module into the Tailwind config needs `allowJs` gymnastics across the
Tailwind/Vite/TS boundary. Duplication with a drift test is this repo's idiom, and
`palette.tailwind.test.ts` is the joint: it reads the config as text and requires a
`token: "#hex"` match for every entry in `PALETTE`.

### `frontend/src/App.tsx` and `routes.tsx` — the shell

Block-level. `TABS` is a three-entry table of path, label, home section and sections; the nav
renders it, and the section rail renders `active.sections` when there is more than one. Two
lines earn a note. The active tab is found with `pathname.startsWith(tab.path)` rather than
`NavLink`'s own `isActive`, because the tab's href points at its home section, so on
`/strategy/live` the STRATEGY link would report itself inactive — `aria-current` is set from
the same test that drives the styling, so the screen reader and the underline can never
disagree. And every link is built as `{ pathname: tab.home, search }`, carrying the current
query across the hop; that is the 5.13 property the whole demo rests on.

`routes.tsx` nests the eight sections and then lists the redirects:

```tsx
      { path: "replay", element: <KeepQuery to="/strategy/replay" /> },
      { path: "live", element: <KeepQuery to="/strategy/live" /> },
      ...
      // an old bookmark or a typo lands inside the shell, not on react-router's bare
      // error page, which would ship without the R-07 footer (spec: every view)
      { path: "*", element: <KeepQuery to="/strategy/setup" /> },
```

`KeepQuery` is a ten-line component that reads `useLocation().search` and hands it to
`<Navigate>`. A plain redirect would drop `?run=`, `?seed=` and the counterfactual's
`?year=&round=&driver=` — which is the entire payload of a demo link — and land the viewer
on a configured section with nothing configured. The catch-all route matters for a reason
that has nothing to do with routing: react-router's own error element renders outside `App`,
so a typo'd URL would show a page with no R-07 footer, and R-07 says every view.

The demo's own links moved with the app: the deep link is now `/strategy/live?...` and the
counterfactual `/analysis/counterfactual?...` in the README, `scripts/warm_demo.sh`, the e2e
spec and `docs/demo/script.md`. The six old paths still redirect, query intact, because a
dead URL in a dissertation is a bad look even when nothing depends on it.

### `frontend/src/views/strategy/stints.ts` — the derivation, line by line

This is domain logic, so every line gets a reason.

```ts
export function stintsFromFrames(frames: LapFrame[], carId: number): Stint[] {
  const stints: Stint[] = [];

  for (const frame of frames) {
    const car = frame.cars.find((candidate) => candidate.id === carId);
    if (car === undefined) continue;
```

One pass over the frames in served order. `find` by id rather than index because the cars
array is ordered by the server's own convention and a car can be absent from a frame; a
missing car is skipped rather than treated as a gap, since a gap would invent a stint
boundary out of a serialisation detail.

```ts
    const current = stints[stints.length - 1];
    // a compound change without in_pit means the two served signals disagree; split
    // anyway, because a stint drawn in one colour over two compounds is a lie either way
    const boundary = current === undefined || car.in_pit || current.compound !== car.compound;
```

Three ways to open a stint, in the order they matter. No stint yet, so this is lap one.
`in_pit` — the authoritative signal, `pit_count > prev.pit_count`, which catches the
same-compound stop and the failure-forced pit. And a compound change without a pit, which
the server should never produce; keeping it is a deliberate belt-and-braces choice, because
if the two signals ever disagree the alternative is drawing one coloured block over two
compounds, which is a worse lie than an extra boundary.

```ts
    if (!boundary) {
      current.endLap = frame.lap;
      current.laps = current.endLap - current.startLap + 1;
      continue;
    }
    stints.push({ compound: car.compound, startLap: frame.lap, endLap: frame.lap, laps: 1 });
```

Not a boundary: extend the open stint to this lap and recompute its length from the
endpoints rather than incrementing a counter, so `laps` cannot drift out of step with
`startLap`/`endLap` if a frame is ever skipped. A boundary: open a new stint on this lap,
one lap long, on the compound the car is now carrying.

```ts
export function pitLapsFromStints(stints: Stint[]): number[] {
  return stints.slice(1).map((stint) => stint.startLap);
}
```

Every stint's first lap is a stop except the first, which is the grid. `slice(1)` is the
whole rule. This function exists separately so the cross-check test can compare its output
against the energy ledger's non-zero `EnergyLap.pit` laps — two independent server paths
reaching the browser, and an off-by-one between them is invisible on a timeline and wrong in
the pit table.

The two regression tests are the shortest useful things in the feature:

```ts
test("a stop onto the same compound still counts as a stop", () => {
```
```ts
test("a failure-forced pit opens a stint even though nothing was changed", () => {
```

Both fail against the old logic. The fix was verified by reverting `boundary` to the
compound-only form and watching three tests go red, including the property loop at
`seed 3: pit on lap 27 opened no stint`. Exercise 2 walks you through it in both directions.

### `frontend/src/lib/queryParams.ts` — writing through the router

```ts
export function useWriteRunBack(): (runId: number) => void {
  const [, setSearchParams] = useSearchParams();
  return useCallback(
    (runId: number) =>
      setSearchParams(
        (current) => {
          current.set("run", String(runId));
          return current;
        },
        { replace: true },
      ),
    [setSearchParams],
  );
}
```

`useSearchParams` is the router's own door onto the query, so a write here updates the
router's location and every `useLocation` consumer re-renders with it. The updater form
(`(current) => ...`) rather than a fresh `URLSearchParams` is what preserves `circuit`,
`seed`, `lap`, `speed` and the counterfactual triple — only `run` is added, so the deep link
stays shareable. `{ replace: true }` keeps the back button pointing where the viewer came
from rather than at the same page minus a run. And the whole thing is wrapped in
`useCallback` so the deep-link effects that call it can list it as a dependency without
re-firing every render — which, given F13's StrictMode ref guards, would mean POSTing a
second race.

The same module holds `positiveIntParam` and `seedParam`, one implementation each, replacing
four hand-rolled parsers across the views that did not agree about what a bad value meant.
`positiveIntParam` rejects 0 and negatives because a bad `?run=` should show the picker,
never fetch `/v1/simulations/NaN`; `seedParam` accepts 0, because 0 is a legitimate seed.

### `frontend/src/views/analysis/` — the two panels the reference faked

`RewardPanel` renders the served keys and nothing else:

```tsx
  const named = Object.entries(terms).filter(([key]) => key !== "total");
  const largest = Math.max(...named.map(([, value]) => Math.abs(value)), 1);
```

`total` is the sum the env appends (`race_env.py:366`), so it is the header figure rather
than a fourth row — showing it as a term would double-count the lap. `largest` is the bar
scale, with a floor of 1 so a lap where every term is tiny does not render three full-width
bars off a 0.001 maximum; the honesty note states the scaling in words, because a bar whose
denominator is invisible is a chart that lies quietly.

The label map is a fallback, not a schema:

```tsx
const TERM_LABELS: Record<string, string> = {
  pace: "pace shaping",
  position: "position (potential-based)",
  terminal: "terminal points",
};
```

```tsx
                label={TERM_LABELS[key] ?? key}
```

Keys with no entry print their own name. That is not defensive coding for its own sake:
`reward_mode="terminal_only"` serves a different set, and F08's penalty arm appends
`violation_penalty`. The panel shows it, unlabelled and honest, rather than either inventing
a caption or silently dropping a term — which is the exact failure mode the six-term
reference panel represents.

`AlternativesPanel` reads the A-03 card's own arrays. The ranking is by probability, and the
one branch that matters is legality:

```tsx
            {option.legal ? (
              <span className="w-12 shrink-0 text-right text-senna-text">
                {(option.prob * 100).toFixed(1)}%
              </span>
            ) : (
              <span className="shrink-0 text-micro uppercase text-senna-ghost">
                {reasons[String(option.action)] ?? "masked"}
              </span>
            )}
```

An illegal action gets its mask reason code where its probability would be, not a 0.0%.
Those are different statements: 0.0% means the policy considered it and did not want it,
while a reason code means the policy was never offered it. That distinction is F-16 rendered
as UI, and the honesty note says so in words — compliance here is by construction, never by
a reward penalty.

### `frontend/src/views/circuit/fitDistance.ts` — the framing maths

```ts
  const halfVertical = (fovDeg * Math.PI) / 360;
  const halfHorizontal = Math.atan(Math.tan(halfVertical) * aspect);
  const half = Math.min(halfVertical, halfHorizontal);
  return radius / (fill * Math.sin(half));
```

`fov` is the full vertical field of view in degrees, so `fov * π / 360` is the half-angle in
radians (divide by 2 for half, by 180 for radians, hence 360). The horizontal half-angle
comes from the vertical one scaled by aspect ratio in *tangent* space, because that is where
a perspective frustum is linear. `min` picks the binding constraint: a landscape panel is
limited by its height, a portrait one by its width. Then the tangency relation for a sphere:
`sin(angular radius) = fill × sin(half)`, inverted for distance. The `radius <= 0` guard
returns 0 and `FitCamera` leaves the camera alone, because a GLB that failed to load has
radius 0 and dividing by it would fling the camera to infinity.

It is a pure function in its own file for one reason: inside `FitCamera` it sat behind a
`useThree()` call that the jsdom mock short-circuits, so the only new maths in the feature
had no test at all. Extracted, it has seven.

`FitCamera` itself adds one piece of judgement:

```tsx
    const fresh = framed.current !== radius;
    const from = fresh ? OPENING_DIRECTION : camera.position.toArray();
```

A resize refits the distance but keeps the direction the user is looking. At the demo's
circuit beat the presenter has usually orbited somewhere, and a screen-share layout change
snapping the camera back to the opening three-quarter view mid-sentence is the kind of thing
that ends up in the recording. Only a new circuit resets the pose.

One refinement came from looking at the rendered screen rather than the maths: the radius is
half the diagonal of the two *largest* extents, not all three. Elevation is exaggerated 1.5x
by the F04 ribbon config and it is the axis the camera looks down, so folding it into the
bounding sphere inflated the radius and pushed every circuit further away than it needed to
be. The elevation axis is identified as the smallest span rather than assumed, because which
axis carries it depends on the export.

### `frontend/src/honesty.test.tsx` — the guard

One test per 5.10.2 statement, each string pinned verbatim as it ships. The pattern is the
same six times: render the section at a path with a stubbed fetch, then `findByText` the
sentence. The one place it does something cleverer is the replay caption:

```tsx
import { ILLUSTRATIVE_MOTION_CAPTION } from "./components/TransportControls";
```

Imported rather than retyped, because two replay-shaped views state it and a copy in the
test would let the component and the test drift together into agreement about the wrong
string. That is a general rule for pinned copy: pin the *identity* where one exists, the
literal only where there is no shared source.

## What we deliberately did not build

Three absences, each with a reason a reviewer can check.

**No planner and no strategy score.** The agent decides lap by lap; there is no search over
race plans anywhere in the codebase. A "89.0/100" badge would be a number with no
computation behind it, in a project whose whole claim is that every number traces to a
response id.

**No points on the Strategy page.** `summary.points` is real, but `terminal_points`
(`senna/env/reward.py:41-47`) divides the FIA table by `points_divisor: 2.5`
(`configs/env.yaml:22-23`), so a P2 finish serves as 7.2 rather than 18. Quoting it verbatim
reads as wrong to anyone who knows the sport, and multiplying it back by 2.5 in the browser
would put a client-computed number on screen, which `frontend/CLAUDE.md` forbids outright.
Position sidesteps both and is what a strategy page is about. `StrategyView.test.tsx` has a
test named *no points appear anywhere, because the served figure is RL-scaled*.

**No pit service-time column.** The reference shows one reading 2.4s. `senna/env/engine.py:100`
computes `pit_time_s`, adds it into `lap_time_s` and never copies it into `info`, so it never
reaches the API. The pit table has four columns and a test pins the set, so nobody can fill
that gap later with a plausible-looking figure.

## How it connects

F23 adds nothing to the 5.1 diagram below the browser line. It rearranges what sits above
it.

```
              configs/*.yaml  ──►  API  ──►  every figure on screen
                                    │
   docs/reference_images/           │        (unchanged: no backend edit in F23)
        (aesthetic only)            │
             │                      ▼
             ▼            ┌──────────────────────────────┐
      palette.ts  ───────►│  App shell: 3 tabs + rail    │◄── R-07 footer, every tab
             │            └──────────────┬───────────────┘
      tailwind.config.js                 │  query carried on every hop (5.13)
      (mirrored, drift-tested)           │
                            ┌────────────┼────────────┬──────────────┐
                            ▼            ▼            ▼              ▼
                      01 STRATEGY    02 CIRCUIT   03 ANALYSIS   legacy paths
                      setup·replay·live   │       energy·tyres·      │
                            │             │       decisions·cf   KeepQuery
                            │             │            │         (query kept)
                   stints.ts (in_pit)  FitCamera   RewardPanel
                   PitSchedule         (GLB bounds) AlternativesPanel
                            └─────────────┴────────────┘
                                    one canvas at a time (5.10.3 / F-28)
                                    every 5.10.2 statement (honesty.test.tsx)
```

Nothing server-side changed. Every number the new sections show was already being served:
stints from `/frames`, reward terms from the frame's `agent.reward_terms`, alternatives from
the `/decisions` card, circuit characteristics from `CircuitDetail`.

## Try it yourself

All commands from `frontend/`.

1. **See the shape of the suite.**

   ```
   npx vitest run
   ```

   You'll know it worked when you get 38 files and 199 tests green. The pre-F23 baseline was
   30 files and 155 tests; the 44 new ones are mostly guards rather than features, which is
   the honest description of this feature.

2. **Break the stint derivation, then break the test that should have caught it.** In
   `src/views/strategy/stints.ts`, change the `boundary` line to the old form:

   ```ts
   const boundary = current === undefined || current.compound !== car.compound;
   ```

   Run `npx vitest run src/views/strategy/stints.test.ts`. You'll know it worked when three
   tests go red and the property loop prints `seed 3: pit on lap 27 opened no stint` — a
   replayable seed, not a vague failure.

   Now the half that teaches something. Leave the code broken and also revert the test to how
   it shipped first: change the generator's `if (stops && random() >= 0.15)` back to
   `if (stops)`, delete the converse block (the `boundaries` `Set` and the loop under it), and
   delete the two named tests at the bottom of the file. Run it again. Six tests pass, 500
   seeded races and all. You are now looking at exactly the state the feature was in when both
   reviewers found the bug by reading code. Restore both files with
   `git checkout src/views/strategy/` and write down, in one sentence, what you would ask of a
   property test before believing it.

3. **Delete an honesty statement.** In `src/views/strategy/StrategyView.tsx`, remove the
   `Pit service time is not shown because it is not served.` sentence from the `HonestyNote`.
   Run `npx vitest run src/honesty.test.tsx`. You'll know it worked when *the strategy section
   states the stints are read back, not planned* goes red on the second assertion — and you
   can say what the state of the world was before this file existed (green, silently). Revert.

4. **Put the illegible grey back.** In `src/config/palette.ts` set `ghost` to `#515c63`, the
   value actually sampled from the reference. Run
   `npx vitest run src/config/palette.tailwind.test.ts`. You'll know it worked when the drift
   test fails on `senna.ghost` — because `tailwind.config.js` still holds the shipped hex. Now
   notice what did *not* fail: nothing measures contrast. That check lives in the review
   battery and in your eyes, the same way F13's GL-clear smearing lives on the runtime
   checklist, and for the same reason — jsdom cannot see it. Revert.

5. **Write to the URL behind the router's back.** In `src/components/RunPicker.tsx`, replace
   the `setSearchParams(...)` call with the old three lines:

   ```ts
   const query = new URLSearchParams(window.location.search);
   query.set("run", String(accepted.run_id));
   window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
   ```

   Run `npx vitest run src/routeMount.test.tsx`. You'll know it worked when *a run started
   after mount reaches the nav and the 5.13 jump links* times out waiting for `run=` in
   `router.state.location.search` — the address bar would have been right and the router's
   location wrong. Revert.

6. **Watch the demo path end to end.**

   ```
   make up && make demo-warm
   ```

   Open the `/strategy/live?...` link it prints, let the decision card arrive, then click
   "compare with the real race" under it and "where the energy went" under the delta chart.
   You'll know it worked when both land configured, with the same `?run=` you started with,
   and the energy view opens on the SOC trace rather than its own picker. That is 5.13's
   one-click property surviving a shell rebuild by a different mechanism than the one the
   spec named.

## Check yourself

1. Saad's reference screenshots show a reward panel with six terms and an "Optimal Strategy
   89.0/100" score. Defend the decision to adopt the reference's look while refusing both
   panels, and say what replaced them.

2. Why do the six spec views become sections on a rail rather than one scrolling page? Name
   the spec ID and the failure mode.

3. The stint derivation reads `in_pit` rather than watching the compound change. Give both
   cases where the two disagree, with the mechanism in `engine.py`.

4. A property test ran 500 seeded races over the broken stint code and passed. Explain the
   two independent reasons, and say what you changed to fix each.

5. Defend this design choice: an illegal action in the alternatives panel shows its mask
   reason code where its probability would be, rather than showing 0.0%.

---

### Answers

1. **A reference tells you how something should look; it cannot tell you what is true about
   your system, and copying a fabricated panel into a dissertation about interpretability
   would undermine the one claim the project is making.** SENNA has no planner, no beam
   search and no strategy score — the agent decides lap by lap — and the reward has exactly
   three terms (pace shaping, potential-based position, terminal points). Both replacements
   came from payloads the API already served and are stronger than the fakes: the real
   three-term decomposition read out of the lap's `reward_terms`, and the card's own masked
   action probabilities, which are literally the options the policy weighed, with illegal
   ones struck through and labelled by the rule that forbade them. Two further reference
   panels — the lap record and the invented track-characteristic scores — were dropped for
   want of an endpoint and replaced with F04 artifacts that exist.

2. **5.10.3 (with F-28) allows one mounted canvas at a time, and a scrolling page would
   co-mount two the moment the boundary between two canvas sections crossed the viewport.**
   Routes solve it by construction: navigation unmounts the old element tree, so at most one
   canvas can exist, and `routeMount.test.tsx` proves it by watching the document with a
   MutationObserver and asserting the peak count never exceeds 1 across all eight sections.
   The tab shell is what a route table looks like when you want three groupings instead of
   six flat links.

3. A stop onto the compound already fitted, and a pit forced by a tyre failure. In
   `_apply_pits` (`senna/env/engine.py:173-179`), `changed = pit != STAY_OUT` is true for the
   first, so `pit_count` increments, but `np.where(changed, pit, state.compound)` writes back
   the value the car already had — and nothing in `masks.py` forbids re-fitting the current
   compound. For the second, `changed` is false so the compound is untouched, but
   `pit_count += (changed | failed)` still fires. `in_pit` is served as
   `pit_count > prev.pit_count` (`senna/serve/frames.py:55`) and catches both, because it is
   the field the writer actually writes; compound change is only a usual consequence of a
   stop.

4. First, the generator could not produce the failing input: it changed the compound on every
   stop, so no seed could ever reach a same-compound or failure-forced stop. Second, the
   assertion only ran one direction — every stint boundary is a pit lap — which the broken
   code satisfies trivially, since a compound change without a pit is a state the server
   cannot produce. The direction that bites, every pit lap opens a stint, was never written.
   The generator now re-fits the same compound one stop in seven, the converse assertion
   collects the boundaries into a `Set` and checks every `in_pit` frame against it, and two
   named tests cover the cases directly. All three go red against the old code, which is how
   the fix was verified.

5. **0.0% and "masked" are different facts: the first says the policy considered the action
   and did not want it, the second says the policy was never offered it, and collapsing them
   would hide the architectural claim the project makes about compliance.** F-16's position is
   that legality comes from action masks and physics clipping — 100% compliant by
   construction — never from reward penalties, and the panel is the one place a viewer can
   see that mechanism operating on a real lap, with the reason code naming which rule applied.
   Printing 0.0% instead would also be false in a subtler way: the masked probability is not
   small, it is undefined, because the mask is applied before the distribution is normalised.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Aesthetic baseline, not content model | F23 | A visual reference is adopted for its grammar and refused for its claims: the F23 screenshots carried DRS, a 20-car grid, six invented reward terms and a planner score, and each honest replacement came from a payload the API already served. |
| Authoritative signal vs correlated consequence | F23 | Stints derive from `in_pit` (`pit_count > prev.pit_count`), not from the compound changing, because a stop onto the same compound and a failure-forced pit both increment the count without touching the value (`engine.py:173-179`). |
| Generator support and the missing converse | F23 | A property test proves nothing about inputs its generator cannot produce, or about the direction its assertion does not run: 500 seeded races passed against the stint bug because every generated stop changed compound and only "every boundary is a pit lap" was asserted. |
| Router state vs the browser history API | F23 | `window.history.replaceState` updates the address bar and tells react-router nothing, so `useLocation` kept serving the pre-run query; `useSearchParams`' updater form writes through the router and preserves the rest of the deep link. |
| Query-preserving redirects (5.13 deep links) | F23 | `KeepQuery` reads `useLocation().search` into `<Navigate>` so the six legacy paths keep `?run=`, `?seed=` and the counterfactual triple; the catch-all also routes typos inside the shell, because react-router's error element ships without the R-07 footer. |
| Contrast as a correctness property | F23 | The sampled `ghost` measured 2.79:1 against the ground and carried R-07 plus every 5.10.2 statement at 11px, so both faint tones were lifted past 4.5:1 — matching a reference stops where matching it makes the disclaimers unreadable. |
| Honesty statements under test | F23 | `honesty.test.tsx` pins every 5.10.2 "what this is not" sentence verbatim (importing the shared caption rather than retyping it), closing the hole where a restyle could delete any of them with the suite still green. |
| Fit the camera to the content | F23 | `fitDistance` solves `sin(angular radius) = fill x sin(half-angle)` on the tighter frustum dimension against the GLB's own bounds, so every circuit fills the panel — one fixed distance can only be right for one of 3-7 km. |
