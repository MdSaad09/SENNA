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

Everything above was written before anyone looked at the rendered pages. When Saad did,
his verdict was that the dashboard gave him neither numbers nor any way to see the system
working, and he was right. The replay was 22 shapes going round a loop with no figure
anywhere near them. The circuit was a two-pixel hairline in a black void. The SHAP bars
said `compound_is_so…`. Three more commits went in on top — `24938ba`, `c5d1a71`,
`a84d6a4` — and the second half of this lesson is about them, because the honest summary
of the first half is that it built correct plumbing and unreadable pages.

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
geometry, and it took three goes to get right — the camera section below tells the whole
story, including the two answers that were confidently wrong.

**A test suite proves behaviour, not communication.** At the end of the first wave the
frontend suite was 38 files and 200 green tests, two subagent reviews had passed, and the
ship gate was clean. The pages were still unreadable. That is not a contradiction, it is
the boundary of what a suite can hold an opinion about: every test asks whether the code
does what the code says, and none of them ask whether a person looking at the result
learns anything.

The timing tower makes the point twice. Before it existed, no test was failing, because
"the replay shows no numbers" is not a behaviour any assertion was making a claim about —
`CarState` carried position, gap, compound, tyre age and in-pit, and the scene read every
one of them to place the cars, then rendered none of them as text. And once the tower
existed but a flex rule pushed it off the right edge, it was still in the DOM with all 22
rows: `getByTestId("timing-tower")` would have found it, queried it, and passed. jsdom has
no layout engine at all — no widths, no overflow, no viewport — so present and visible are
the same thing to it. The viva version: **the frontend suite can prove that a component
renders the served value, but "on screen and readable" is outside what jsdom can express,
so looking at the artefact is a separate verification step with its own findings** — it
belongs on F11's runtime checklist beside draw calls, fps and bloom.

**`min-w-0`, the one word that hides a panel.** A flex item's `min-width` defaults to
`auto`, which computes to its content's intrinsic size, so `flex-1` grows freely and
refuses to shrink past what it contains. The replay's canvas section had carried `min-h-0`
since F11, which is the same rule on the other axis and the right fix while it lived in a
flex column. Moved into a flex row beside a tower, it needed `min-w-0` and did not have
it, so the canvas claimed its content width and the 16rem `shrink-0` sibling was pushed
out of the box. This bit twice, replay and live, with identical symptoms: the panel exists,
the tests are green, the screen shows nothing.

**Raw internals are not interpretability.** The decision card's driver bars printed the
observation names straight from `senna/explain/features.py`, truncated to a 7rem column:
`compound_is_so…`, `last_lap_harve…`. There is a temptation to call that the honest
version, since it is literally what the model saw. It is not. A reader who cannot parse the
label cannot check the claim, so the raw name does not transfer honesty to the reader, it
transfers work to someone who does not have the source open. `featureLabels.ts` maps all 32
dims to plain English, keyed by served name, and an unknown key falls through to the raw
name — so the failure mode of a rename is an ugly label rather than a confident wrong one.

**A unit test cannot see a join.** `RewardPanel` has four tests and every one of them
constructs `terms` and passes it in: `render(<RewardPanel terms={SERVED_TERMS} />)`. All
four are good tests, and none of them could notice that the panel's one caller was looking
up `terms` with a lap number that did not exist. The component was correct in isolation for
weeks while the panel never appeared on the page. The general shape: **a unit test fixes
the inputs, so it can only ever check the half of the contract below the seam; the half
above it — who calls this, with what — is only checked by something that runs both sides.**

Name-checked and not re-taught: the one-canvas rule and react-router (F11), the jsdom WebGL
boundary and runtime checklist (F11), seeded property loops (F11), the idempotent
`insertFrame` buffer (F13), the decision-timing rule (F14), provenance comments (F00),
stylised provenance for visual data (F04), and E-15's empty-explanations state (F10, F13).

## The code, guided

Reading order: the language, the shell, the stint derivation, the two honest panels, the
camera, the guard. Then the second wave, in the order the screenshots complained: the
tower, the markers and the road, the race chart, the labels, the join, the rail, the
circuit's numbers. Then the third: the tyre chart and the liveries.

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

The last refinement came from looking at the rendered screen rather than the maths, and it
took two goes — worth telling honestly, because the first go was a confident wrong answer.

The fit originally framed a **bounding sphere** around the circuit. Albert Park still filled
only about 40% of the panel, which is the exact complaint the fit existed to answer. The
first diagnosis was that elevation was to blame: the F04 config exaggerates it 1.5x, and it
is the axis the camera looks down, so surely it was inflating the radius. That change was
made, measured — and made no difference at all. A circuit spans a couple of kilometres
across and perhaps thirty metres up; `hypot(2000, 1500, 30)` is `hypot(2000, 1500)` to three
decimal places. The reasoning was plausible and the arithmetic said no.

The real cause is that a circuit is a **flat, irregular curve viewed from 45 degrees**, and a
sphere around a flat curve is mostly empty air. So the radius is now the circuit's
*silhouette* — the furthest any vertex sits from the axis the camera looks along:

```ts
const along = px * ux + py * uy + pz * uz;
const perpendicular = Math.max(px * px + py * py + pz * pz - along * along, 0);
```

That is Pythagoras: split each vertex into the part along the view axis and the part across
it, and keep the largest across. The foreshortening of the 45-degree view is taken out for
free, because it is already in the geometry. Fitted at `RIBBON_VIEWPORT_FILL = 0.82`, the
silhouette circle projects to about 79% of the panel's tighter half-dimension, and the
track inside that circle reads smaller again because an irregular outline is not a circle.
The view prints that 79% under a "framing" header, so the number on screen is the measured
one rather than the requested one.

The lesson here is not about cameras. It is that "plausible cause, confident fix" survived
right up until it was measured, and only measuring killed it.

**The third attempt, which was not about framing at all.** Two more things were wrong and
neither was the maths.

The first is embarrassing and worth saying plainly: `FitCamera` was only ever mounted in
the circuit explorer. The replay drew its ribbon through the same `useRibbon` hook, computed
the same radius, and never used it — so Bahrain ran off the bottom of the panel while the
circuit page framed the identical model perfectly. One line in `ReplayScene` fixed it:

```tsx
      <group position={[-cx, -cy, -cz]}>
        <FitCamera radius={ribbon.radius} />
```

It sits inside the recentred group for readability only; what makes it work is that the
group puts the circuit's centre at the origin, which is where `FitCamera` points the camera
(`camera.lookAt(0, 0, 0)`).

The second is that framing was never the whole complaint. A correctly framed 5.2 km circuit
drawn at its true 12 m width is about two pixels of road: a hairline in a void, which is
exactly what the screenshot showed. So the ribbon is now drawn three times its real width:

```ts
export const RIBBON_WIDTH_EXAGGERATION = 3;
```

```ts
function widenRibbon(positions: Float32Array): Float32Array {
  const widened = positions.slice();
  for (let i = 0; i < widened.length; i += 6) {
    for (let axis = 0; axis < 3; axis++) {
      const left = widened[i + axis];
      const right = widened[i + 3 + axis];
      const centre = (left + right) / 2;
      widened[i + axis] = centre + (left - centre) * RIBBON_WIDTH_EXAGGERATION;
      widened[i + 3 + axis] = centre + (right - centre) * RIBBON_WIDTH_EXAGGERATION;
    }
  }
  return widened;
}
```

Line by line, because this is geometry. `slice()` copies rather than mutating in place, and
that is load-bearing: `ribbonPositions` hands back the mesh attribute's own array, which
belongs to the GLTF that `useGLTF` caches and shares across every component that loads the
same circuit, so widening in place would restretch the same buffer by another 3x every time
anything rebuilt the ribbon. The stride is 6 because
F04 writes each station as two vertices, left edge then right edge (F11's centreline
rebuild depends on that layout). The inner loop runs over x, y and z, so a banked or climbing
section widens in its own plane rather than being flattened. `centre` is the midpoint of the
two edges, which *is* the centreline — so scaling both edges about it leaves the centreline
numerically untouched, and every car position, arc-length table and annotation strip built
downstream is unaffected. And `widenRibbon` is applied inside `useRibbon` before
`buildCentreline` and before the bounds scan, so the X-mode and braking strips widen with the
road and the camera fit accounts for the wider silhouette.

Two exaggerations now sit on the same model, and the interesting part is that they are
applied in different places for different reasons. Elevation's 1.5x is baked into the
committed GLB by the F04 pipeline (retuning it needs `make circuits`); width's 3x is applied
in the browser, so the exported artifact stays true to the surveyed geometry and only the
picture is stretched. Both are `stylised` in `config/constants.ts` and both are quoted on
screen, in the legend, next to each other:

```tsx
        <li>
          track drawn {RIBBON_WIDTH_EXAGGERATION}x its real width — at true scale a 12 m road
          on a multi-kilometre circuit is about two pixels
        </li>
```

That is F-12 working as designed: a visual choice is allowed, as long as the viewer is told
the number. The same argument covers `CAR_MARKER_SCALE = 6` in the replay — a 5.6 m car on a
framed 5.2 km circuit is about one pixel, so the markers are drawn six times life size and
the transport caption now ends "car markers are drawn well above life size so they can be
seen at circuit zoom". Extending that caption needed no test edit, for the reason the guard
section below gives — and it is worth being clear about what the guard buys: pinning the
identity proves the sentence is on screen, never that it is still true of the code.

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

### `frontend/src/components/TimingTower.tsx` — the numbers that were already there

93 lines, one table, no fetch. That is the whole point of it: every column is a field of
`CarState` that `ReplayScene` was already reading to place the cars, so the tower needed no
endpoint, no schema change and no computation. It is the cheapest panel in the feature and
the one that changed the replay from decoration into an instrument.

```tsx
export default function TimingTower({ cars, egoId, onSelect, selectedId }: TimingTowerProps) {
  const order = [...cars].sort((a, b) => a.position - b.position);
```

The spread is not stylistic. `sort` mutates, and `cars` is either react-query's cached frame
(replay) or a frame inside the zustand buffer (live) — reordering it in place would corrupt
shared state and, worse, would do it without changing any reference react is watching, so
the corruption would render late and look like a different bug. Sorting by `position` rather
than trusting array order is the same instinct as `find` by id in `stints.ts`: the cars array
is ordered by the server's own convention, which is car id, not classification.

```tsx
function gapLabel(car: CarState): string {
  if (car.position === 1) return "leader";
  if (car.gap_ahead_s === null) return "—";
  return `+${car.gap_ahead_s.toFixed(1)}`;
}
```

Three lines that mirror the server exactly. `frames.py:63-66` serves `gap_ahead_s` as `None`
in precisely two cases — the leader, who has nobody ahead, and a retired car, whose frozen
clock would otherwise print a nonsense or negative gap. So the first branch names the leader
case in words, the second prints an em dash for the case where the server declined to
compute, and neither invents a number. One decimal because the underlying quantity is a
difference of lap-quantised cumulative times; more digits would suggest a resolution the
simulator does not have.

`in_pit` gets a red PIT flag, and it is the same `pit_count > prev.pit_count` signal the
stint derivation reads — so a same-compound stop and a failure-forced pit both light the
flag, for the reasons in the stints section above. The ego row is tinted with the accent, the
compound is a colour chip with `title={car.compound}` rather than a letter, and the row calls
`onSelect`, which drives the existing `selectedCarId` in both stores, so clicking a name in
the tower selects that car in the 3D scene.

### `RaceReplayView.tsx` and `LiveSimulationView.tsx` — the flex rule, twice

```tsx
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* min-w-0: without it the canvas sizes to its content in a flex row and shoves
            the timing tower off the right edge */}
        <section className="relative min-h-0 min-w-0 flex-1">
```

Block-level, but the comment is the lesson: `flex-1` is grow-1, shrink-1, basis-0, and the
shrink is floored by `min-width: auto`. A canvas host's intrinsic width is whatever the
canvas was last sized to, so the section ratchets — it grows and then declines to give the
space back, and the `shrink-0` aside next to it goes off the edge of an `overflow-hidden`
parent. Nothing anywhere errors. Both views had the identical fault from the identical
cause: the section was written when it was the only child of a flex column.

The live view's tower selector is worth reading closely:

```tsx
  const carsNow = useLiveStore(
    (state) =>
      state.frames[
        Math.min(Math.max(0, Math.ceil(state.playheadLap) - 1), state.frames.length - 1)
      ]?.cars,
  );
```

`playheadLap` is fractional, because F11 interpolates positions between laps; `ceil` takes it
to the lap being run into, and `-1` turns a lap number into an array index. `max(0, …)`
covers the moment before the first frame lands. `min(…, length - 1)` is the one that matters:
during a live race the playhead legitimately runs ahead of what has streamed, and without the
clamp the selector returns `undefined` and the tower vanishes at exactly the point the race
is most interesting. Clamping shows the newest real frame instead, which is late by under a
lap and never wrong. Because F13's `insertFrame` returns the same array reference for a lap
it already holds, this selector's result is reference-stable within a lap, so zustand
re-renders the tower once per lap rather than once per animation frame.

### `frontend/src/views/strategy/RaceStoryChart.tsx` — the race as one picture

The stint timeline says what tyres the agent used and the pit table says when it stopped.
Neither tells you whether any of it worked. This chart draws position against lap for all 22
cars, so the stops, the field and the safety cars are one glance rather than three panels.

```ts
function positionRows(frames: LapFrame[]): Record<string, number>[] {
  return frames.map((frame) => {
    const row: Record<string, number> = { lap: frame.lap };
    for (const car of frame.cars) row[`c${car.id}`] = car.position;
    return row;
  });
}
```

Recharts is row-oriented: you hand `LineChart` one array of objects, and each `<Line>` names a
`dataKey` to pull out of every object. The served shape is the transpose of that — a list of
laps, each holding a list of cars — so this is a pivot, one row per lap with 22 columns named
`c0`…`c21`. The `c` prefix matters more than it looks: integer-like object keys are
enumerated ahead of string keys by JavaScript's own rules, so bare car ids would shuffle
`lap` to the end of every row and make the data awkward to read in a debugger, and it keeps
each `dataKey` unambiguously a series name.

```tsx
          {/* reversed: P1 belongs at the top, the way a classification reads */}
          <YAxis
            reversed
            domain={[1, fieldSize]}
            ticks={[1, 5, 10, 15, 20]}
            stroke={CHART.axis}
            fontSize={11}
            width={28}
          />
```

`reversed` is the whole readability argument. Position is a rank where smaller is better, so
drawn on a normal axis the agent's good laps travel downwards, which every reader parses for
half a second as losing places. Reversed, P1 is at the top and gaining places moves the line
up, which is how a classification is read on every timing screen in the sport. `domain` is
pinned to the field size rather than left to autoscale, so a race where the agent never leaves
the top six does not silently rescale into looking like a fight for the lead.

The rest is paint order and honesty. Safety-car and VSC laps are shaded first as
`ReferenceArea`s spanning `lap ± 0.5`, because on a discrete lap axis a single lap has zero
width and would draw nothing. The 21 rivals are drawn next in `CHART.axis` grey at 45%
opacity, then the stop laps as dashed accent `ReferenceLine`s, then the agent last, so SVG
paint order puts the line you care about on top of the ones you do not. Every series sets
`dot={false}` and `isAnimationActive={false}`: 22 series times ~57 laps is over a thousand
circles nobody asked for, and a chart that re-animates on every re-render is noise during a
demo. `ticks={[1, ...stopLaps, lastLap]}` labels the laps where something happened instead of
an even grid — the axis is annotation, not measurement.

### `frontend/src/config/featureLabels.ts` — plain English for 32 dims

```ts
export const FEATURE_LABELS: Record<string, string> = {
  lap_progress: "how far into the race",
  ...
  last_lap_harvest_frac: "energy recovered last lap",
```

```ts
export function featureLabel(name: string): string {
  return FEATURE_LABELS[name] ?? name;
}
```

Every wording is a reading of the comment beside that dim in `senna/explain/features.py`,
which is the one place the 32-slot contract is written down (5.5.1). Two design choices are
examinable. The map is keyed by the *served* name, not by index, so reordering the observation
vector cannot shift every label by one — a reordering is invisible here and an index-keyed map
would have relabelled every bar silently. And the lookup falls through to the raw name, so a
renamed feature degrades to `tyre_grip_est_v2` on screen: ugly, obviously an internal name,
and impossible to mistake for a claim.

The file lives in `config/`, which means `provenance.test.ts` picked it up with no changes —
and the tag it carries is honest about what kind of artifact it is: `stylised — the wording
only`. The numbers are the SHAP values, untouched; the only thing invented here is English.

### `frontend/src/views/analysis/DecisionsView.tsx` — an off-by-one that hid a panel

```tsx
  const card = available.find((entry) => entry.lap === selectedLap) ?? available[0];
  // decision cards number laps from 0 (the observation's lap index at decision time)
  // and frames from 1, so joining on equality found nothing and this panel silently
  // never rendered. Match the frame the decision was taken on.
  const rewardTerms = frames.data?.find((frame) => frame.lap === (card?.lap ?? -1) + 1)?.agent
    .reward_terms;
```

The two lap numbers come from the same field and mean different things, and the reason is
`worker/jobs.py::_episode`:

```python
        action = np.asarray(actor.act(obs, info, env.action_masks()))
        obs, _, terminated, _, info = env.step(action)
        frame, snapshot = build_lap_frame(env, info, snapshot)
```

`actor.act` runs first and the logging actor records `info["lap"]`, which is `state.lap`,
documented in `state.py` as "laps completed; 0 at the grid". Then `step` advances the race and
`build_lap_frame` reads the same field after the increment. So the decision taken on the grid
is card lap 0 and the lap it produced is frame lap 1, all the way down. This is F14's
decision-timing rule showing up as a serialisation detail: the action for lap L is chosen
against the state at the end of lap L−1, and the two artifacts each label themselves with the
lap they belong to.

The symptom was specific and nasty. `/decisions` returns cards ordered by `lap_number`
(`api/routes/simulations.py:190`), so `available[0]` is lap 0, and no frame has lap 0 — the
panel was absent every single time the page loaded. Click any other lap and it *did* render,
showing the next lap's reward terms, which is the worse failure because it looks fine. The
live view was never affected: its store does `cards.set(frame.lap, card)` as the socket
delivers them together, so nothing there has to reconstruct the pairing.

Both `RewardPanel` tests and the `honesty.test.tsx` statement test passed throughout, the
first because they hand `terms` straight to the component, the second because its fixture
happens to contain a frame at the card's lap number. Neither is a bad test. They are just
tests of the wrong seam.

### `frontend/src/views/strategy/RaceSetupRail.tsx` — the controls stay on screen

Block-level, because most of it is a form. The change in behaviour is that the Strategy tab
no longer swaps between "picker" and "results": the rail is permanent down the left side and
the results fill the rest, so what produced the race on screen is readable beside the race.
Before this, `StrategyView` returned early when `runId === null` and rendered a centred
`RunPicker`, which meant that the moment a run existed the configuration vanished.

Two blocks earn line-level attention. First, the rail has to follow the loaded run:

```tsx
  const [slug, setSlug] = useState<string | null>(currentCircuit);
  const picked = useRef(false);

  useEffect(() => {
    if (!picked.current && currentCircuit !== null) setSlug(currentCircuit);
  }, [currentCircuit]);
```

`useState(currentCircuit)` only reads its argument on the first render, and on that render the
run row has not arrived from react-query yet, so the initial value is `null` and the rail falls
back to the first circuit in the library. That is how it came to read 58 laps beside a 57-lap
race. The effect adopts the circuit when the run resolves. `picked` is a ref rather than state
because it must not cause a render and it is not displayed — the moment the user clicks a
circuit themselves, their choice outranks the loaded run forever.

Second, the request body:

```tsx
        // omit defaults so the request body stays byte-identical to the other pickers'
        // and the E-15 cache key namespace does not fork on equivalent requests
        ...(era !== "2026" ? { era } : {}),
        ...(weather !== "dry" ? { weather_profile: weather } : {}),
        ...(band !== "test" ? { rival_band: band } : {}),
```

Now go and check that comment, because it is the kind of claim this project's whole method
says you should not take on trust — and it turns out to be over-claiming. `sim_cache_key`
(`senna/serve/cache.py`) builds its digest from `getattr(req, name)` over the *validated*
`SimulationCreate`, and 5.9.2 gives `era`, `weather_profile` and `rival_band` literal
defaults of `"2026"`, `"dry"` and `"test"` — the same values the rail treats as default. So
pydantic has already filled them in before the digest is taken, and the two spellings hash
identically. The stored `config` is `req.model_dump()`, which also includes defaults, so that
does not differ either. Omitting the fields is harmless and slightly tidier over the wire,
and it does not do the thing the comment says it does.

Keep the habit rather than the fact: **when a comment names a mechanism, read the
mechanism.** The E-15 key lives in one 47-line file, so checking cost two minutes and turned
"I believe this" into "I have read this" — which is the only difference that matters in a
viva. The genuine version of the rule is F15's: `?lap=` and `?speed=` stay out of the body
because they really would fork the key.

The grid control is now a slider, `min={1} max={22}`, sourced from `SimulationCreate`'s
`ge=1, le=22` (5.9.2), with the readout in the accent and a "top ten / outside the top ten"
caption under it.

### `LapStrip.tsx` and `TrackCharacteristics.tsx` — the circuit page gets numbers

Block-level. The circuit tab was a 3D model and a rail of text; it now carries the lap
unrolled into a horizontal strip with the X-mode sections and braking zones positioned by
`start_m / lap_length_m`, plus a table of every detected braking zone with its entry speed,
minimum speed and the drop between them. All of it was already in `CircuitDetail`. The zones
are detected by the F04 pipeline at a 50 km/h drop within a 100 m window
(`configs/ribbon.yaml`, spec 5.10.1 item 6), and the honesty note under the table says so in
those words, because "braking zones" sounds like an official corner table and is in fact a
reading of one fast lap.

The legend moved off the canvas and into the rail. It had been floating bottom-left over the
model, covering the circuit it was describing — a small thing, and a fair example of the kind
of defect that only exists once something is on screen.

### `frontend/src/views/tyres/GripCurves.tsx` — when the spec's picture cannot say it

The tyre page was the last one Saad looked at, and his question was the right one: what am I
supposed to understand from this? A small flat green shape in a black panel, and two boxes
of text.

Two causes, and the second is more interesting than the first. The framing bug you already
know — the surface is 320 units square and the shared `CAMERA` sits 1273 units back because
it was sized for a 5 km ribbon, so the same `FitCamera` fix applies with
`GRIP_SURFACE_RADIUS_M`.

The second is that the surface is *genuinely* flat, and no camera fixes that. Put Bahrain's
fitted hard compound through its own law:

```
grip(age) = 1 - a * age^b,  a = 0.000878, b = 1.0671
grip(30)  = 1 - 0.000878 * 30^1.0671 = 1 - 0.033 = 0.967
```

Three percent of grip across a whole stint. Spec 5.10.2 asks this view to make "the cliff
visible", and a surface cannot, because the cliff is not on the surface: it is a discrete
failure the simulator enforces at age 33, not a slope the curve reaches. The view was
drawing the wrong kind of object for the fact it was meant to convey.

So the surface keeps its place — 5.10.2 specifies it and it is honest about the temperature
axis being illustration — and the meaning moves to a 2D chart beside it. Every compound the
circuit has, each line stopped at its own cliff, each cliff dashed in the compound's colour.
At Bahrain that reads SOFT 31, HARD 33, MEDIUM 34, and the three decay curves lie almost on
top of each other. Which *is* the finding: at this circuit the compounds barely differ in
how fast they lose grip, and what separates them is how long they survive. That is the trade
the agent is deciding when it pits, and it is the same fact M9 measures from the other end
(37.9 tyre failures per 100 races).

One line worth copying, in the row builder:

```ts
      if (age <= curve.cliff_age) row[curve.compound] = grip(curve, age);
```

Past its cliff a compound has no curve, because it has failed. Extrapolating the fit beyond
the failure it caused would draw a confident line about a tyre that does not exist. The
chart uses `connectNulls={false}` so the line simply stops.

### `frontend/src/config/liveries.ts` — a palette has to include the things that move

The last note Saad made was that the replay's colours did not match the rest of the system,
and he was right in a way the palette work had missed entirely. F23 put every *panel* colour
in one file and never touched the eleven team liveries, which were chosen in F11 against a
neutral-950 scene: a fully saturated wheel, `#e23d3d`, `#3d7be2`, `#3de28f`. Against the new
muted teal they read as a bag of sweets sitting on an instrument.

They still have to separate 22 cars at sprite size, so the fix is to keep the hue spacing and
drop the saturation to the level the rest of the dashboard runs at — hue does the work,
saturation stays out of it. `EGO_ACCENT` also becomes the dashboard mint rather than white,
so "ours" is the same colour in the timing tower, the delta chart and the scene.

The bigger lesson is about scope. "One palette" meant one palette *for panels*; the moving
objects were a separate surface nobody had listed, exactly as the inline chart hexes had been
before this feature found them. And there was a third: the replay was drawing View 1's
braking, harvest and X-mode strips under the cars, painting the whole lap amber and violet so
the cars had to compete with the road for attention. Those strips are what the circuit
explorer is *for*; under a race they are noise, and `withZones={false}` turns them off. **When
you unify a visual language, enumerate every surface that draws — panels, charts, scenes, and
the things moving across them — because the ones you forget are the ones that look wrong.**


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

## Two tests that changed, and why that was allowed

Changing a test to make it pass is usually the wrong move, so it is worth being precise about
the two places the second wave did it.

The setup rail captions its grid slider with the zone the slot sits in. It first read "points
zone", and `StrategyView.test.tsx` went red:

```ts
  expect(screen.queryByText(/\bpoints\b|\bpts\b/i)).toBeNull();
```

That guard is deliberately blunt. It cannot tell the difference between quoting the RL-scaled
`summary.points` — the thing it exists to forbid — and the sporting phrase for the top ten,
and it should not try, because a guard with an exception list is a guard with a way through
it. So the *label* changed to "top ten", not the guard. Cost: one word. Benefit: the rule
stays "no form of the word points appears on this page", which is checkable at a glance and
has no gaps to argue about.

The grid control's test changed for the opposite reason: the thing being tested is now a
stronger guarantee than it was. As a number input, the assertion was
`gridPosition.validity.rangeOverflow` — the user could type 23, the browser marked the field
invalid, and the form declined it. As a range input, 23 is not a value the control can hold
at all:

```ts
  fireEvent.change(gridPosition, { target: { value: "23" } });
  expect(gridPosition.value).toBe("22");
  expect(screen.getByTestId("grid-readout")).toHaveTextContent("P22");
```

Rejection is a thing that happens after a mistake; clamping means the mistake has no
representation. The second assertion is not decoration — checking `value` alone would pass on
a control whose readout had drifted from its input, and P23 on screen beside a clamped 22 in
the body is exactly the class of bug this test is for. The rule of thumb: change the test when
the code's guarantee has genuinely become stronger or the test's claim was wrong; change the
code when the test is enforcing something you still want.

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
                   RaceSetupRail       FitCamera    RewardPanel
                   stints.ts (in_pit)  (silhouette) (card.lap + 1)
                   PitSchedule         widenRibbon  AlternativesPanel
                   RaceStoryChart      LapStrip     featureLabels.ts
                   TimingTower ────────┘            (32 dims, plain English)
                   (replay + live)
                            └─────────────┴────────────┘
                                    one canvas at a time (5.10.3 / F-28)
                                    every 5.10.2 statement (honesty.test.tsx)
```

Nothing server-side changed, in either wave. Every number the new sections show was already
being served: stints and the race chart from `/frames`, the tower's four columns from the
same `CarState` the 3D scene places cars with, reward terms from the frame's
`agent.reward_terms`, alternatives and SHAP drivers from the `/decisions` card, the lap strip
and braking table from `CircuitDetail`. The second wave added no fetches at all — it rendered
payload that was arriving and being thrown away.

## Try it yourself

All commands from `frontend/`.

1. **See the shape of the suite.**

   ```
   npx vitest run
   ```

   You'll know it worked when you get 38 files and 200 tests green. The pre-F23 baseline was
   30 files and 155 tests; the 45 new ones are mostly guards rather than features, which is
   the honest description of this feature. Note the other number: the second wave added seven
   components and 200 is also what the suite said before it. Exercise 7 is about that.

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

5. **Stop writing the run id through the router.** The Strategy tab now starts its races from
   the rail, so this is the path `routeMount.test.tsx` exercises. In
   `src/views/strategy/StrategyView.tsx`, delete the `writeRunBack(id);` line from `start`,
   leaving only `setRunId(id)`:

   ```tsx
   const start = () => {
     return (id: number) => {
       setRunId(id);
     };
   };
   ```

   Run `npx vitest run src/routeMount.test.tsx`. You'll know it worked when *a run started
   after mount reaches the nav and the 5.13 jump links* times out waiting for `run=` in
   `router.state.location.search`, printing `- run=7`. The page itself would have looked
   perfect: the race renders, the header says run 7, and every tab link hands on a URL with
   no run in it. Revert. (`RunPicker.tsx` does the same job for the live and counterfactual
   views, through `setSearchParams` directly — same mechanism, different caller.)

6. **Take the `min-w-0` back off.** In `src/views/replay/RaceReplayView.tsx`, delete `min-w-0`
   from the canvas `<section>`'s class list. Run `npx vitest run src/views/replay` and note
   that nothing fails. Then run `make up`, open a completed run's replay, and watch the timing
   tower not be there. You'll know it worked when you can find all 22 `<tr data-car=...>` rows
   in the browser's element inspector while seeing none of them on screen. That gap — present
   in the DOM, absent from the page — is the whole reason the screenshots caught what the
   suite could not. Revert.

7. **Give the tower its first test.** The second wave added seven components and no test file:
   `TimingTower.tsx`, `RaceStoryChart.tsx`, `LapStrip.tsx` and `featureLabels.ts` are untouched
   by the suite, and `RaceSetupRail.tsx` is reached only sideways, through
   `StrategyView.test.tsx`'s grid assertions. That is the honest state of it. Write `src/components/TimingTower.test.tsx` with two
   cases: cars handed in car-id order render in classification order, and the leader's row
   reads `leader` while a car with `gap_ahead_s: null` and `position: 5` reads the em dash.
   You'll know it worked when both pass, and when reversing the sort comparator turns the first
   one red. Then ask yourself the F14 question — would either test have failed on the code as
   it shipped? If not, they are documentation, which is fine, but say so.

8. **Break the feature-label fall-through.** In `src/config/featureLabels.ts`, change
   `featureLabel` to `return FEATURE_LABELS[name] ?? "unknown feature";`, then rename
   `soc_frac` to `battery_soc_frac` in the map. Nothing in the suite fails. Now reason about
   what a viewer would see: every card whose top pit driver is the battery would read "unknown
   feature" beside a large SHAP bar, which is a claim about the model that is not true. Restore
   both, and write one sentence on why fall-through to the raw name is the safer default for a
   label map that is not the source of truth.

9. **Re-join the decision cards on the wrong lap.** In `src/views/analysis/DecisionsView.tsx`,
   drop the `+ 1`:

   ```tsx
   const rewardTerms = frames.data?.find((frame) => frame.lap === card?.lap)?.agent.reward_terms;
   ```

   Run `npx vitest run src/views/analysis src/honesty.test.tsx`. Everything passes, including
   the honesty test that renders this very panel — its fixture card sits at lap 14 and its
   frames run to 20, so a frame exists at the wrong number. Then open the section against a
   real run and watch the reward panel be absent on arrival and one lap late after a click.
   Restore the `+ 1` and write down where a test would have to sit to catch this.

10. **Watch the demo path end to end.**

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

6. The suite was green, both reviews passed, and the pages were unreadable. Say what a test
   suite can and cannot establish here, and name the specific thing about jsdom that makes
   "the tower was pushed off screen" unassertable.

7. Defend this design choice: SHAP bars are labelled "energy recovered last lap" rather than
   `last_lap_harvest_frac`, in a project whose whole argument is that nothing is a black box.

8. The reward decomposition never appeared on the Decisions section, and every test around it
   passed. Explain the off-by-one, where it comes from in the env, and why the live view was
   immune.

9. The circuit ribbon is drawn three times its real width and the car markers six times life
   size. Justify that in a dissertation about interpretability, and say how it differs from
   the elevation exaggeration you already had.

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

6. **A suite establishes that the code does what the code says; it has no opinion about
   whether a person reading the result learns anything, so looking at the artefact is a
   separate verification step that produces its own findings.** Two concrete failures show the
   boundary. No test was failing when the replay showed no numbers at all, because "there
   should be a timing tower" was not a claim anything was making. And when the tower existed
   but a missing `min-w-0` pushed it out of an `overflow-hidden` flex row, it was still in the
   DOM with all 22 rows, so any query would have found it — jsdom implements the DOM but no
   layout or rendering engine, so it has no widths, no overflow and no viewport, and "off
   screen" is not a state it can represent. That is the same boundary as F11's WebGL mock and
   F13's GL-clear smearing, and it is why the runtime checklist exists.

7. **A label a reader cannot parse does not transfer honesty, it transfers work — the point of
   the card is that a non-author can check the claim, and `compound_is_so…` truncated in a
   column defeats that entirely.** The mapping is one line of English per dim, each read off
   the comment beside it in `senna/explain/features.py`, and the numbers it sits next to are
   untouched SHAP values. Two properties keep it honest: it is keyed by the served feature
   name rather than by index, so reordering the observation vector cannot shift every label by
   one, and an unknown key falls through to the raw name, so a rename produces an obviously
   internal string instead of a confident wrong caption. The raw name is still available on
   hover via `title`.

8. Decision cards carry `info["lap"]` as read *before* `env.step`, and lap frames carry the
   same field read *after* it (`worker/jobs.py::_episode` calls `actor.act` then `env.step`
   then `build_lap_frame`), and `state.lap` is documented as "laps completed; 0 at the grid".
   So the grid decision is card lap 0 and produces frame lap 1, and the join needs
   `frame.lap === card.lap + 1`. `/decisions` is ordered by lap number, so the default card is
   lap 0, no frame matches, and the panel was absent on every page load; selecting any other
   lap rendered the next lap's terms, which is the worse half. The live view never had the
   problem because the socket delivers a card with its frame and the store writes
   `cards.set(frame.lap, card)` — no reconstruction, no join. The four `RewardPanel` tests
   pass `terms` in directly, so they test the component below the seam and can say nothing
   about who calls it.

9. **Both are visual exaggerations of a stylised layer that carries no data, both are declared
   on screen with their factor, and F-12 is exactly the rule that permits that: decoration may
   be adjusted, it may not be presented as measurement.** At true scale a 12 m road and a
   5.6 m car on a framed 5 km circuit are about two pixels and one pixel, so drawing them
   truthfully communicates nothing while claiming to be faithful. The difference from
   elevation is where it is applied: elevation's 1.5x is baked into the committed GLB by the
   F04 pipeline, so the artifact itself is stretched and retuning it needs `make circuits`,
   whereas the width 3x is applied in the browser inside `widenRibbon`, so the exported
   geometry stays true to the survey and only the picture changes. Nothing downstream shifts
   either way: the widening scales both edge vertices about their midpoint, which is the
   centreline the car positions and annotation strips are built from.

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
| Looking at the artefact is a verification step | F23 | 200 green tests, two reviews and a clean gate shipped pages with no readable numbers on them: a suite checks that the code does what it says, never that a reader learns anything, and jsdom has no layout engine so "pushed off screen" is not a state it can represent. |
| `min-width: auto` on flex items | F23 | A flex item will not shrink below its content, so a canvas host with `flex-1` and no `min-w-0` claimed its content width and pushed the `shrink-0` timing tower out of an `overflow-hidden` row — twice, replay and live, with every test green. |
| Plain-English feature labels (interpretability is for the reader) | F23 | `featureLabels.ts` maps all 32 observation dims to English, keyed by served name with fall-through to the raw name, because `compound_is_so…` truncated in a column moves the work onto a reader who does not have `features.py` open. |
| The seam a unit test cannot see | F23 | `RewardPanel`'s four tests construct `terms` and pass it in, so they could not notice that its only caller joined decision cards (laps from 0) to frames (laps from 1) and found nothing — the panel was correct and never rendered. |
| Stated exaggeration, applied where it belongs | F23 | Elevation's 1.5x is baked into the F04 GLB; the ribbon's 3x width and the car markers' 6x are applied in the browser so the exported geometry stays true, and the legend and caption quote both factors (F-12). |
| Change the label, not the guard | F23 | The setup rail's "points zone" caption tripped the blunt `/\bpoints\b/i` no-points guard, so the wording changed: a guard with an exception list has a way through it, and one word is cheaper than a weakened rule. |
