# F11 — The dashboard shell, the circuit explorer and the race replay

## What we built and why

Everything before this feature ends in a Postgres row or a JSON body. F11 is the first
thing an examiner can *watch*: open a browser, pick Bahrain, see the ribbon F04 built
with its braking, harvest and X-mode zones painted on; then start a simulation and
watch 22 cars run the race the frozen agent drove, scrub back to the pit window,
click the agent's car. Six views exist as navigation from day one — circuit, replay,
energy, tyres, live, counterfactual — but four of them are honest placeholders that
say which feature delivers them. F11 ships the shell and the first two.

Two constraints shape every file. The first is the frame budget (5.10.3): the replay
must hold 60 fps with a 45 fps floor, which in React terms means the thing updating
sixty times a second must never be React. The second is the interpretability contract
crossing the browser boundary for the first time (5.1 invariant 2): every number on
screen came from an API response, and the dev overlay can show you which one. Where a
pixel is decoration rather than data — the harvest strip, the mid-lap car motion, the
pit pull-aside — the UI says so in words, on screen, driven by flags the API sends.

This is also your first real week in the frontend stack. F00 installed all of it and
taught you why the pins exist (React 18 with R3F 8, never 19/9); it taught nothing
about how any of it works. That is this lesson's other half.

## New ideas in this feature

**React: components and re-renders.** A React component is a function that takes
props and returns a description of UI; React runs it, diffs the result against what
is on screen, and patches the difference. When state changes, React re-runs the
function and every child below it. That machinery is brilliant for a form and fatal
for animation: a render allocates objects, rebuilds element trees and diffs them,
and at 60 fps you have about 16 ms per frame for *everything* — physics sampling,
matrix writes, the GPU submit. The cardinal sin in this codebase is any state update
that makes React render per frame. The rule everywhere in F11: React renders when
the *lap* changes or the user clicks; everything per-frame mutates three.js objects
through refs, behind React's back. Watch for the three escape hatches below —
`useRef`, `getState()`, and transient subscriptions — they are all this one rule.

**three.js: scene graph, meshes, draw calls.** three.js is the browser's standard 3D
library. Its world is a scene graph: a tree of `Object3D` nodes, each with a
position, rotation and scale that compose down the tree. The visible leaves are
meshes, and a mesh is a pairing of a *geometry* (vertex buffers — exactly the
positions-plus-indices layout you met in the F04 GLB) with a *material* (a compiled
GPU shader program plus its settings). Every mesh the camera can see costs one *draw
call* — one CPU-to-GPU round trip per frame — and draw calls, not triangles, are
what usually kills a frame budget. That is why 5.10.3 budgets replay at ≤ 150 calls,
and why 22 cars are not 22 meshes (next idea but one).

**@react-three/fiber: JSX for the scene, useFrame for the loop.** R3F is a React
renderer whose output is a three.js scene graph instead of DOM. Lower-case JSX
elements map to three constructors — `<mesh>`, `<boxGeometry args={[w, l, h]}>` —
and React's diffing now creates and disposes three objects, which is what makes
"navigation unmounts the canvas" a real cleanup mechanism rather than a hope. The
second half of the bridge is `useFrame(callback)`: R3F runs your callback inside the
render loop, once per frame, with the elapsed `delta`. The division of labour to
hold on to: JSX declares *structure* once; `useFrame` mutates *transforms* every
frame; and nothing in a `useFrame` body may touch React state, or you have committed
the cardinal sin with extra steps.

**react-router: views are URLs.** The router maps paths to elements in one route
table and swaps the mounted element when the URL changes. Swapping means the old
view *unmounts* — every effect cleanup runs, R3F disposes the scene, the canvas
element leaves the DOM. That is the entire F-28 enforcement mechanism: the shell
owns no canvas, each canvas view owns exactly one, so "at most one WebGL context
alive" is a property of the architecture, not of anyone's discipline. Version note:
`react-router-dom ^6.30`, chosen in the plan because the v6 line is stable on React
18 and carries no React-19 pressure — and `npm ls react` was checked after install
to prove the tree still resolves a single react 18.3.1 (the 5.9.1 failure mode).

**zustand: a store outside React.** zustand keeps state in a plain module-level
object with three doors in. A hook with a selector —
`useReplayStore((s) => s.playing)` — subscribes a component to one slice, and it
re-renders only when that slice changes. `useReplayStore.getState()` reads without
subscribing at all, which is what a `useFrame` loop wants: fresh state every frame,
zero renders. And `subscribe(selector, callback)` — a *transient subscription* —
runs a plain callback on change, so the scrub slider can write `slider.value`
straight into the DOM sixty times a second while React never hears about it. Mental
model: a notice board outside the React building; components can pin a "tell me
when this line changes" note, or just walk past and read it.

**react-query: server state is a cache, not useState.** Data that lives on the
server is different from UI state: several components want it, it goes stale, it
retries. react-query declares each fetch as a query with a key
(`["circuit", slug]`), caches results by key, dedupes concurrent callers, and
handles polling via `refetchInterval` — that is how the replay view watches a
queued run flip to `complete` without hand-rolled timers. One line in
`queries.ts` is doctrine: `staleTime: Infinity` on a finished run's frames, because
the E-16 store never rewrites a completed race (F10) — the cache is allowed to
believe that forever.

**InstancedMesh and the label atlas: one draw call, many things.** An
`InstancedMesh` draws one geometry-plus-material N times in a single draw call,
with a per-instance 4×4 matrix (position, heading, scale) and optional per-instance
attributes — colour for the liveries, and a custom UV offset for the labels. The
label atlas takes the same idea to text: all 22 car codes are pre-drawn into one
canvas texture, and each label instance is a quad whose shader picks its cell out
of the atlas. Result: every car body, every detail fin and *every piece of sprite
text* on track costs three draw calls total. The viva answer: **22 cars are one
InstancedMesh with per-instance colour, and all non-podium labels are one atlas
quad mesh with per-instance UV offsets, so the whole field renders in three draw
calls against 5.10.3's budget of 150; only the podium and the selected car get real
DOM labels, capped at four (F-28).**

**vitest and jsdom: testing a GPU app with no GPU.** vitest is the vite-native test
runner; jsdom gives it a DOM implementation in Node — elements, events, `render` —
but no layout and no WebGL, so a real `<Canvas>` cannot mount. The strategy has two
halves. Everything with logic worth testing lives in `lib/` as pure functions —
centreline math, progress unwrapping, the label budget — and tests run them
directly. At the component level, R3F is mocked at the Canvas boundary: `<Canvas>`
becomes a bare `<canvas>` tag, drei's `Html` a plain div, `useGLTF` a fixture —
which is exactly the observable F-28 cares about (how many canvases exist), while
draw calls, bloom and real context loss go on a named runtime checklist the ship
report carries. What jsdom cannot see, a human verifies with the dev overlay.

Already in the ledger and only name-checked here: the F-27 browser boundary and
provenance comments (F00), the GLB positions-plus-indices layout, arc-length
resampling and the F-12 stylised rule (F04), and the E-16 playback source of truth
this whole view reads (F10).

## The code, guided

Reading order follows the story: shell, canvas, geometry, View 1, motion, View 2,
provenance, and the tests that came first.

### frontend/src/routes.tsx and App.tsx — the shell owns no canvas

The route table is F-28 written as structure: `App` is the layout parent (header,
`<Outlet/>` where the active view renders, footer), and each of the six children is
a whole view. Neither `App` nor `main.tsx` mounts a `<Canvas>` — only
`CircuitExplorerView` and `RaceReplayView` do, each through `CanvasHost` — so two
canvases can only coexist if the router mounts two routes at once, which it cannot.
The file's header comment records one plan divergence honestly: imports are eager,
not lazy, because the router's `lazy` path builds a `Request` object jsdom's
AbortSignal cannot satisfy, and a single-page dashboard ships every view to every
visitor anyway.

`App.tsx` is block-level: a nav header of `NavLink`s (the active one styled via the
`isActive` render prop), the backtick listener for the dev overlay — with a guard
so typing a backtick into a form field doesn't toggle it — and this, verbatim on
every route because it sits above the `<Outlet/>` swap:

```tsx
      {/* R-07: the unofficial-project footer stays on every view */}
      <footer className="border-t border-neutral-800 px-5 py-1.5 text-xs text-neutral-600">
        Unofficial student project — not affiliated with F1, the FIA or any team
      </footer>
```

### components/CanvasHost.tsx and ContextLossOverlay.tsx — one canvas, held politely

`CanvasHost` is the single `<Canvas>` a view may own. Block-level, it wires four
things: the device-pixel-ratio clamp (`DPR_RANGE = [1, 2]` — a 3x retina panel
would silently triple the pixels shaded), the camera constants, the context-loss
hook, and `onCreated`, which reads the GPU's renderer string once and lets the
heuristic pick the bloom default (conservative: unknown or hidden renderer means
off; the user's toggle then owns it). One line deserves line-level attention:

```tsx
        <group rotation={[-Math.PI / 2, 0, 0]}>{children}</group>
```

three.js is Y-up: Y is "up" on screen. The F04 GLB is Z-up: X/Y is the ground plane
and elevation rides the third component, because that is how the track data came out
of FastF1. Rather than remap axes in every consumer — centreline, strips, car
matrices, corner posts — one rotation group turns the whole data space upright, and
everything inside it keeps thinking in track coordinates. The cost surfaces exactly
once, in the replay's billboard math, and you'll see it handled there.

`ContextLossOverlay` is E-18. Browsers reclaim WebGL contexts under memory pressure
— too many tabs, a driver reset — and without handling, the canvas just goes black,
which reads as a crash. Two details are the whole lesson. First:

```ts
    const onLost = (event: Event) => {
      event.preventDefault();
      setContextLost(true);
    };
```

`preventDefault` on `webglcontextlost` is the WebGL contract: the *default* is that
the context is gone for good, and preventing it tells the browser you want a
`webglcontextrestored` later. The test asserts `defaultPrevented` directly, because
forgetting that line changes nothing visible until the day a real context dies.
Second, the overlay itself is DOM, not WebGL, and its state lives in the zustand
`uiStore` — you cannot draw an apology *with* the dead context, so the message
renders next to the canvas, not inside it.

### lib/centreline.ts — rebuilding the racing line from ribbon triangles

The clever bit of the feature. The GLB stores only what the eye needs: ribbon
triangles. But cars are placed by *distance along the lap*, so the frontend needs a
centreline it can sample by arc length — and F04's export makes that recoverable,
because the vertex layout is disciplined: station `i` keeps its left edge at vertex
`2i` and its right edge at `2i + 1`. This file is core geometry, so line by line.

```ts
  for (let i = 0; i < stations; i++) {
    const l = i * 6;
    const r = l + 3;
    lefts.push([positions[l], positions[l + 1], positions[l + 2]]);
    rights.push([positions[r], positions[r + 1], positions[r + 2]]);
    centres.push([
      (positions[l] + positions[r]) / 2,
      ...
```

`positions` is a flat `Float32Array`, three floats per vertex, two vertices per
station — hence the stride of 6 and `r = l + 3`. The midpoint of each left/right
pair is a centreline point; the edges are kept too, because the zone strips lerp
from centre toward edge. Then the arc-length table:

```ts
  const cumS = new Float32Array(stations);
  for (let i = 1; i < stations; i++) {
    ...
    cumS[i] = cumS[i - 1] + Math.hypot(bx - ax, by - ay, bz - az);
  }
  const total = cumS[stations - 1] + Math.hypot(fx - lx, fy - ly, fz - lz);
```

`cumS[i]` is metres travelled from the start line to station i — the same
cumulative-distance idea as F04's arc-length resampling, rebuilt on the receiving
end. `total` adds the closing segment from the last station back to the first,
because a lap is a ring, not a polyline. Sampling is where the loop's CPU cost
lives:

```ts
function ringLerp(points, cumS, total, s_m) {
  const s = ((s_m % total) + total) % total;
```

The double modulo maps *any* real number onto [0, total): JavaScript's `%` keeps
the sign of its left operand, so `-5 % 40` is `-5`, and tangent sampling reaches
behind the start line. Then:

```ts
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (cumS[mid] <= s) lo = mid;
    else hi = mid - 1;
  }
```

Binary search for the last station at or before `s`. The comment in the file states
the reason as a cost: the replay samples every car, every frame — 22 cars × 60 fps
× (position + tangent) — and a linear scan over ~2,700 stations would be the
biggest CPU item in the loop. O(log n) makes it noise. The remainder linearly
interpolates within the found segment, with `(i + 1) % n` closing the ring on the
last segment. `tangentAt` is a central difference — sample half a metre ahead and
behind, subtract, normalise — cheap and smooth enough to point a car; nothing needs
the true analytic derivative.

### views/circuit/ — View 1, the annotated circuit

`CircuitRibbon` opens with a deliberate refusal: it never mounts `gltf.scene`. It
pulls the raw `POSITION` array out of the loaded GLB and builds its own
`BufferGeometry` — the triangle indices are ten lines of the same `2i / 2i+1`
arithmetic, closing the ring with `(i + 1) % stations`. The stated reason is
lifetime ownership: drei's `useGLTF` caches loaded scenes globally, and mounting a
cached scene means R3F and the cache disagree about who disposes it when the route
unmounts. Geometry we built, we dispose — there is an effect that does exactly
that, because prop-attached geometries sit outside R3F's declarative auto-dispose.

The zone overlays come from `lib/ribbonStrips.ts` (block-level: for each
`[start_m, end_m]` zone, walk the stations inside the range, drop paired vertices
lerped from centreline toward each edge, lift them `ANNOTATION_LIFT_M` above the
deck to dodge z-fighting, and split any zone whose `start_m > end_m` — one that
crosses the start line — into two runs so no triangle bridges the s = 0 seam). One
strip call carries the feature's most examinable honesty decision:

```tsx
      // harvest happens under braking (MGU-K), so its stylised strip rides the
      // same zones, narrower and a step higher so both stay visible
      harvest: zoneStrip(braking, HARVEST_WIDTH_FRACTION, ANNOTATION_LIFT_M * HARVEST_LIFT_STEPS),
```

No harvest-zone data exists anywhere — F04 never emitted it (plan divergence 2).
The choice was: draw nothing, invent zones, or draw the physically defensible thing
and label it. Harvest is rendered as a narrower strip over the braking zones —
which is where an MGU-K actually harvests — and the per-lap cap H_max comes from
the API's per-circuit `h_max_mj`, never a literal. The viva answer: **harvest zones
have no source data, so the UI draws them where the physics says harvesting happens
— under braking — and labels the choice "stylised" in the legend, with H_max quoted
from the API; presenting decoration as data would breach F-12, and silently drawing
nothing would hide a real energy mechanic the spec asks View 1 to teach (5.10.2
row 1).**

`Legend.tsx` is that honesty rendered from data. The caveat lines are derived from
`detail.flags` — the `meta.json` flags F04 wrote, which F11's one backend touch
passes through the API verbatim (`flags: dict | None` on `CircuitDetail`, plan
divergence 1, pinned by `test_detail_passes_the_meta_flags_through_verbatim`). A
flat-plus-camber circuit says "no Z data, rendered flat"; a smoothed one quotes the
exaggeration factor. Hardcoded caveat copy would rot the first time a ribbon is
rebuilt with different flags; this cannot.

`CornerMarkers` is block-level: one InstancedMesh of cylinder posts placed by
`corner.distance_m` through `centreline.sampleAt` — the meta's corner x/y are raw
FastF1 decimetres at 10x the mesh scale and deliberately unused — plus one drei
`Text` per number, affordable because View 1 is static and sits at ~27 draw calls
against a budget of 150. The picker around all of this renders the whole
25-circuit library with coverage badges: a circuit without a built ribbon gets an
honest "ribbon not built" state driven by the F-08 coverage flags, never a crash
(plan divergence 5).

### lib/progress.ts — from lap snapshots to motion that never reverses

The simulator is lap-quantised. Each car gets one `s_track` per lap — F10's
display-only lap fraction, synthesised from gap-to-leader and folded mod 1
(frames.py). To animate between laps you need two things: fractions unwrapped into
a number that only grows, and an interpolant that cannot overshoot. Core logic,
line by line.

```ts
export function unwrapProgress(sByLap: number[]): number[] {
  ...
  for (let lap = 1; lap < sByLap.length; lap++) {
    const delta = sByLap[lap] - sByLap[lap - 1];
    unwrapped.push(unwrapped[lap - 1] + delta - Math.round(delta) + 1);
  }
```

`delta` is the raw fraction change, somewhere in (−1, 1). Subtracting
`Math.round(delta)` removes the mod-1 wrap: a car at fraction 0.9 that reappears at
0.1 has delta −0.8, round −1, so the wrap-corrected change is +0.2. Adding 1
restores the whole lap the snapshot cadence implies. The hidden assumption, stated
in the header comment: the true per-lap advance sits in (0.5, 1.5) laps — true for
anything still racing; a car lapped hard enough to break it just folds onto its
visual position, which the UI already labels illustrative. The property test
generates truths with advance 1 ± 0.3 and proves fractions and advances both
survive the round trip.

`monotoneCubic` is Fritsch-Carlson: a cubic Hermite spline whose tangents are
limited so the curve is monotone wherever the data is.

```ts
  const tangent: number[] = [slope[0]];
  for (let i = 1; i < n - 1; i++) {
    tangent.push(slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2);
  }
  tangent.push(slope[n - 2]);
```

Endpoints take the one-sided slope. Interior tangents average the neighbouring
slopes — unless the slopes disagree in sign or either is zero, which forces a flat
tangent, because a local extremum or plateau in the data must stay one. Then the
guard that gives the method its name:

```ts
    const a = tangent[i] / slope[i];
    const b = tangent[i + 1] / slope[i];
    const radius = a * a + b * b;
    if (radius > 9) {
      const scale = 3 / Math.sqrt(radius);
      tangent[i] = scale * a * slope[i];
      tangent[i + 1] = scale * b * slope[i];
    }
```

Fritsch and Carlson proved the cubic on a segment is monotone whenever the
normalised tangent pair (a, b) lies inside a region that the disc of radius 3
safely under-approximates; any pair outside is pulled back onto the circle. Delete
this block and 34 of the property test's 100 seeded cases go red (I checked). The
alternative everyone reaches for first is Catmull-Rom, which runs tangents through
neighbours with no limiting and overshoots at any sharp change — an overshoot in
*progress* is a car visibly driving backwards for half a second. The viva answer:
**mid-lap positions are interpolated between per-lap snapshots, so the interpolant
must be monotone by construction — Fritsch-Carlson limits Hermite tangents so a
car can never reverse, where Catmull-Rom trades that guarantee for smoothness we
don't need; the motion is labelled illustrative on screen either way (5.10.2
row 2).** Evaluation clamps outside the knot range: before lap 1 and after the
flag, cars hold their known positions rather than extrapolate.

### views/replay/ — View 2, the one useFrame

`RaceReplayView` is block-level plumbing with the E-16 shape: read `?run=` off the
URL, poll the run row until `complete` (react-query's `refetchInterval`), fetch all
frames over REST in `FRAMES_PAGE_SIZE` pages until the first short page, and only
then mount `ReplayScene`. Scrubbing is a read, never a re-simulation — this view is
the browser-side client of F10's stored-frames decision. The header strip shows the
agent's SOC, harvest and deploy for the lap in view, straight from the frame; the
grid size is `frames[0].cars.length`, never a hardcoded 22, because era-2024 runs
carry 20 cars.

`ReplayScene` owns the only per-frame work in the app. The discipline first:

```tsx
  useFrame(({ camera }, delta) => {
    useReplayStore.getState().tick(delta, nominalLapS, maxLap);
    const { playheadLap } = useReplayStore.getState();
```

`getState()`, not a hook — the loop reads the store without subscribing, so
advancing the playhead sixty times a second re-renders nothing. `tick` delegates to
the pure `advancePlayhead`: the playhead moves `delta × speed / nominalLapS` laps,
so 1x means one wall second per simulated second — the same clock definition as
F10's WebSocket, deliberately, with `nominal_lap_s` arriving in the run summary.
At `maxLap` it clamps and pauses instead of running off the data.

```tsx
  const scratch = useRef({
    carrier: new Object3D(),
    camLocal: new Vector3(),
    billboard: new Quaternion(),
    ...
```

Every vector and quaternion the loop needs is allocated once and reused. `new` in a
60 fps loop is how you buy garbage-collector pauses, and a GC pause is a dropped
frame; this is the frame-loop equivalent of the hot-loop rule that keeps pandas out
of `step()` (F05).

```tsx
    parent.worldToLocal(camLocal.copy(camera.position));
    // billboard sprites in local space: undo the parent's world rotation, keep the camera's
    parent.getWorldQuaternion(billboard).invert().multiply(camera.quaternion);
```

Here is the Z-up group's one deferred cost. The cars live inside the rotated group,
so the camera's position must be pulled into that local space before distances mean
anything, and a sprite that should face the camera must wear "the camera's rotation
as seen from inside the group" — parent world rotation inverted, camera rotation
kept. Do this per frame, not per car: it is the same for all 22.

Then the per-car body, line by line:

```tsx
    for (const track of tracks) {
      const progress = track.progressAt(playheadLap);
      const s_m = (((progress % 1) + 1) % 1) * lapLength;
      const [x, y, z] = ribbon.centreline.sampleAt(s_m);
      const [tx, ty, tz] = ribbon.centreline.tangentAt(s_m);
```

`tracks` was built once per run in a `useMemo`: per car, `monotoneCubic` over the
unwrapped fractions, keyed by lap number. Evaluate it at the playhead, take the
fractional part (double modulo again), scale by lap length, and the centreline
gives position and direction. Retired cars need no special case here — frames.py
froze their `s_track` server-side, so the unwrap sees a flat line and the
interpolant, exact at flat knots, parks the wreck (F10's orbit bug, fixed at the
source).

```tsx
      const inPit = atFrame.cars[track.id]?.in_pit ?? false;
      if (inPit) {
        aside.copy(up).cross(heading).normalize();
        position.addScaledVector(aside, PIT_LATERAL_OFFSET_M);
      }
```

No pit-lane spline exists (an F04 gap the plan records rather than papers over —
divergence 3). Up × heading is the lateral direction; an in-pit car pulls 9 m
aside and shrinks to 0.7 scale, and the transport caption owns the honesty in
words. Then three matrix writes per car — body at full scale; detail fin at scale
zero beyond `LOD_DISTANCE_M` (500 m, sourced 5.10.3 — zeroing the instance matrix
*is* the LOD, since three's LOD object cannot act per instance); sprite label
raised `LABEL_HEIGHT_M`, wearing the billboard quaternion, hidden when the car is
beyond LOD *or* holds one of the four DOM labels — followed by the three
`instanceMatrix.needsUpdate = true` flags that tell three to re-upload.

React's only involvement is deliberately lap-rate:

```tsx
  const labelLapIndex = useReplayStore((state) => frameIndexAt(state.playheadLap, frames));
```

The selector quantises frame-rate state into lap-rate renders: `playheadLap`
changes every frame, but the selector's *output* — which frame index the playhead
is in — changes once per lap, and zustand only re-renders when the output changes.
That render recomputes the labelled set through the pure `labelledCars` (podium
plus selected, ≤ 4 — the F-28 budget as a function the property tests pin), and
the frame loop reads it through a ref so the closure never staleness-bugs.

`CarInstances` holds the three instanced meshes and their two gotchas. Colours are
written in `useLayoutEffect` — before first paint — because three 0.169 will not
quietly retrofit the `instanceColor` attribute onto an already-compiled shader
program. And the sprite shader carries the flipY gotcha:

```glsl
    // flipY is off, so texel v grows down the canvas while the quad's uv.y grows
    // up — mirror v or every code renders upside down
    vUv = aUvOffset + vec2(uv.x, 1.0 - uv.y) * uCellSize;
```

Canvas 2D draws top-down; UV space grows bottom-up. three's default `flipY` hides
this by flipping the whole texture at upload, but the atlas indexes cells by
top-down row, so the texture stays unflipped and the shader mirrors v within the
cell. Both meshes also set `frustumCulled = false`: three culls an InstancedMesh by
its *base geometry's* bounding sphere — a 5.6 m box at the origin — which knows
nothing about instances spread around 5 km of ribbon; leave culling on and cars
vanish when you look away from the start line. This is the classic disappearing-
instances bug, listed in the plan's edge cases before a line was written.

`CarLabels` renders the ≤ 4 drei `Html` slots on stable keys and moves them
imperatively in its own small `useFrame`, reading positions from the map the main
loop maintains — DOM labels follow cars at frame rate while React renders only
when the *set* changes. `PerfProbe` closes the loop on 5.10.3: `gl.info.autoReset`
off, counters reset once per frame (with bloom on, the composer's multiple passes
would otherwise zero mid-frame), sampled at 2 Hz onto the perf bus and
`window.__SENNA_PERF` for the Chrome-trace session, with a console warning past
150 calls. The replay scene runs at ~9 calls (~25 with bloom) — an order of
magnitude of headroom, by construction rather than by tuning.

### api/client.ts, provenance.ts and DevOverlay — the contract in the browser

`client.ts` is the one door: every request resolves against `VITE_API_BASE` —
`/api` behind the vite proxy locally, a public origin in production, never a
Docker hostname (F-27, F00's browser boundary) — and every response is recorded
*before* the caller sees it, failures and non-JSON proxy pages included.
`provenance.ts` is the ring buffer behind that: a module-level store (the zustand
idea with no library — snapshot, subscribe, bounded to `PROVENANCE_LOG_CAP`
entries) holding method, path, status, the `X-Model-Version` header F10 stamps on
every response, and any `run_id` / `model_version` / `env_config_hash` found in
the body. `DevOverlay` renders the ring through `useSyncExternalStore` — React's
built-in bridge to external stores — alongside the live perf numbers coloured
against their budgets, plus a button that calls
`WEBGL_lose_context.loseContext()` so E-18 can be rehearsed on demand instead of
awaited. This is 5.1 invariant 2 made a feature: press backtick and every number
on screen traces to the response that carried it.

### The tests that came first

Sixteen frontend test files, plus the Python flags test, were committed red in one
commit before any implementation existed (F00's forcing function, at its best
here). Three are worth naming.

`routeMount.test.tsx` is the F-28 pin. It renders the *real* route table in
`createMemoryRouter` with Canvas mocked to a bare tag, navigates circuit → replay
→ energy → circuit, asserts exactly one canvas on canvas routes and zero on stubs
— and runs a `MutationObserver` throughout, recording the *peak* canvas count, so
even a one-commit overlap during a route transition would fail the run. The rule
is tested as an invariant over time, not a spot check.

`liveries.f29.test.ts` is the F-29 guardian, and it does not test the livery table
so much as the *repository*: an fs-walk of every shipped file under `src/` plus
`index.html`, against a deny list of team, sponsor and driver marks — full names
lower-cased, short marks like RB behind word-boundary regexes so "rb" inside an
ordinary word cannot false-positive. Test files are excluded from the walk, which
is what lets the deny list spell the names it forbids. It runs in the node
environment (a file-URL detail jsdom breaks), and it means no future feature can
leak a real-world mark into the frontend without a red build.

`progress.test.ts` and `labels.test.ts` are the property tests, written as seeded
loops over `mulberry32` — a twelve-line deterministic PRNG — with the seed printed
in every assertion label, so a red run replays exactly. The viva answer: **the
plan weighed a fast-check dependency against four invariants and chose seeded
loops with printed seeds — the same replayability, no shrinking, and no new
supply-chain surface for a dissertation artifact; the seed in the failure message
is the property-based-testing property that actually matters here.**

## How it connects

```
 browser
 ┌─ shell: routes.tsx / App.tsx — nav, R-07 footer, backtick DevOverlay ──────┐
 │   /circuit ─ CanvasHost ─ CircuitRibbon + strips + Legend(flags)           │
 │   /replay  ─ CanvasHost ─ ReplayScene (one useFrame) ─ CarInstances/Labels │
 │   /energy /tyres /live /counterfactual — stubs for F12/F13                 │
 └────────────┬────────────────────────────────────────────────────────────────┘
              │ api/client.ts → provenance ring (5.1 inv. 2), VITE_API_BASE (F-27)
              ▼
 F10 API: /v1/circuits (+flags, F11's one backend touch) · /v1/simulations
          POST → poll → /frames pages · /api/v1/assets/circuits/*.glb (F04)
              ▲
 lap_frames rows written once by the worker (E-16) — this view only reads
```

F04 built the ribbons this feature samples; F10 serves them and the frames.
F12 fills the energy and tyre routes; F13 brings the WebSocket client, decision
cards and deep links into the same shell.

## Try it yourself

All frontend commands from `frontend/`; compose from the repo root.

1. **The full tour.** `docker compose up --build`, open `http://localhost:5173`.
   Pick Bahrain in the circuit view and read the legend against the canvas — every
   caveat line should have a visible counterpart. Go to replay, start a run (grid 8,
   seed 42), wait for the poll to flip, press play, scrub, click a midfield car,
   then press backtick: check draw calls against 150 and find the POST that started
   your run in the provenance table. Toggle quality and watch the draw-call count
   move; press "simulate context loss (E-18)" and reload from the overlay. You'll
   know it worked when you can point at any number on screen and name the API
   response it came from.

2. **The frontend gate.** `npm test`, then `npx tsc -b`, then `npm run lint` — the
   three checks /ship runs for this half of the repo. You'll know it worked when
   all three are green and you can say which of the three would catch a `s_track`
   field renamed on the API side (tsc, via `api/types.ts`) versus a livery colour
   duplicated (vitest, the F-29 table test).

3. **Predict the paging.** In `config/constants.ts`, set `FRAMES_PAGE_SIZE` from
   100 to 10. Write down how many `/frames` requests a 57-lap Bahrain replay will
   now make and what stops the loop, then load a replay and count the rows in the
   dev overlay. You'll know it worked when you counted six — five full pages, then
   laps 51–60 returning 7 frames, and the short page is the stop condition, no
   total-laps input anywhere. Revert.

4. **Break Fritsch-Carlson.** In `lib/progress.ts`, delete the whole
   `radius > 9` clamp loop and run `npm test -- progress`. You'll know it worked
   when "random non-decreasing knots stay non-decreasing under dense evaluation"
   fails with `seed 846003` in the message — a big slope feeding a near-flat
   segment, the exact overshoot that makes a car reverse — and re-running
   reproduces the same seed. Revert.

5. **Prove the F-29 walk bites.** Add a real driver surname to the deny list in
   `liveries.f29.test.ts`, confirm green, then plant that name in a comment inside
   `config/liveries.ts` and rerun. You'll know it worked when the failure names
   the file and the mark — then remove both edits and think about what this test
   costs (one fs walk) versus what a trademark in the dissertation demo would.

## Check yourself

1. Why must nothing re-render at 60 fps, and what are the three mechanisms the
   replay uses to keep React out of the frame loop?

2. Walk what happens, object by object, when you navigate from /replay to /energy.
   Why is that the F-28 enforcement mechanism rather than a test being one?

3. Defend this design choice: mid-lap car positions are interpolated with a
   Fritsch-Carlson monotone cubic rather than Catmull-Rom — and why is the
   interpolation acceptable at all in a project whose contract says no pixel may
   pretend to be data?

4. The replay renders 22 cars, their liveries and all their on-track text in three
   draw calls. How, and why are there also at most four DOM labels?

5. vitest never sees a draw call, a bloom pass or a real context loss. What does
   the test suite pin instead at the R3F boundary, and where does the rest of the
   assurance come from?

---

### Answers

1. A React render re-runs component functions, allocates element trees and diffs
   them — fine at click rate, ruinous inside a 16 ms frame budget, and any
   `setState` at frame rate drags the whole subtree with it. The replay's three
   escape hatches: per-frame data is mutated through refs (instance matrices,
   scratch vectors — allocated once, reused); the `useFrame` loop reads the
   zustand store with `getState()`, which never subscribes; and the transport
   slider tracks the playhead through a transient `subscribe` callback that writes
   `slider.value` directly into the DOM. React renders at lap rate only, via
   selectors whose *output* (frame index, label set) changes once per lap.

2. The router swaps the route element, so `RaceReplayView` unmounts: every effect
   cleanup runs — the geometry-dispose effects free GPU buffers, the atlas texture
   and sprite material are disposed, listeners detach — R3F tears down the scene
   graph, and the `<canvas>` leaves the DOM with its WebGL context. `/energy`
   mounts a `StubView` that owns no `CanvasHost`, so the canvas count is zero. The
   mechanism is architectural: the shell owns no canvas and only route elements
   do, so two canvases would require two mounted routes, which the router cannot
   do. `routeMount.test.tsx` then *pins* the property with a MutationObserver
   watching the peak count — the test witnesses the architecture, it isn't the
   enforcement.

3. The env is lap-quantised, so on-screen motion between laps must be synthesised
   from one `s_track` snapshot per lap; an interpolant with overshoot turns a
   sharp progress change into a car visibly driving backwards, so monotonicity is
   a correctness requirement, not a preference. Fritsch-Carlson limits Hermite
   tangents (sign guard, flat guard, the radius-3 circle) so the curve is monotone
   wherever the knots are — Catmull-Rom is smoother but unbounded, and the
   property test proves the difference: delete the clamp and 34 of 100 seeded
   cases fail. It is acceptable because it is *declared*: the transport caption
   says mid-lap positions are illustrative and spline-interpolated, the legend
   flags every other stylised element, and the underlying per-lap data is real API
   output — F-12's rule is never that pixels can't be styled, it is that styling
   must not present itself as data.

4. One InstancedMesh draws the geometry N times in a single call with a
   per-instance matrix; the bodies carry per-instance colour (written before first
   render — the three 0.169 compiled-program gotcha), the detail fins reuse the
   same matrices with scale zeroed beyond 500 m, and every non-podium label is an
   instance of one quad mesh whose shader offsets into a single canvas-atlas
   texture (mirroring v, since flipY is off). Three calls, ~9 for the whole scene.
   DOM labels exist because HTML text is sharper and richer than sprite text for
   the cars you're actually reading — but each drei `Html` is a reprojected DOM
   node with real layout cost, so 5.10.3 caps them at four: the podium plus the
   selected car, decided by the pure `labelledCars` the property tests pin.

5. jsdom has no WebGL, so the suite mocks R3F at the Canvas boundary — `<Canvas>`
   becomes a bare tag, `Html` a div, `useGLTF` a fixture — and pins what is
   observable there: canvas counts across navigation (F-28), the label budget,
   legend caveats from a flags fixture, 20-car era-2024 grids. Everything with
   real logic was designed to live below that boundary as pure functions in
   `lib/`, where jsdom tests it completely (centreline, strips, progress, labels,
   atlas layout). The remainder — real draw calls versus 150, the 45 fps trace,
   bloom, GLB parsing, genuine context loss — is a named runtime checklist in the
   ship report, executed against the dev overlay and `window.__SENNA_PERF`, with
   `PerfProbe` asserting the draw-call budget where it is actually measurable.

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| React components and the re-render rule | F11 | UI as functions re-run on state change, diffed and patched; a render costs allocation and diffing, so nothing may re-render at 60 fps — per-frame work mutates three.js objects through refs. |
| three.js scene graph and draw calls | F11 | A tree of Object3D transforms whose mesh leaves pair a geometry (vertex buffers) with a material (shader program); each visible mesh is one CPU-to-GPU draw call, the unit 5.10.3 budgets at 150. |
| @react-three/fiber (JSX scene, useFrame) | F11 | A React renderer targeting three.js: JSX declares scene structure once (and unmounting disposes it), while useFrame callbacks mutate transforms per frame — never React state. |
| react-router and the one-canvas rule (F-28) | F11 | Views are URLs in one route table; navigation unmounts the old element tree, running every cleanup, so "at most one canvas" is architectural — the shell owns none, each canvas view owns exactly one, pinned by a MutationObserver peak-count test. |
| zustand and transient subscriptions | F11 | A store outside React with three doors: hook selectors re-render on slice change, getState() reads without subscribing (the useFrame door), and subscribe(selector, cb) drives DOM writes at frame rate with zero renders. |
| react-query server state | F11 | Fetches declared as cached queries keyed by queryKey, with deduping and refetchInterval polling; staleTime: Infinity on finished-run frames encodes E-16's "stored frames never change". |
| InstancedMesh, per-instance attributes and the label atlas | F11 | One geometry drawn N times in a single call with per-instance matrix, colour and custom attributes; all 22 cars plus one atlas-textured quad mesh for sprite text is three draw calls, with frustumCulled off because the base bounding sphere knows nothing about instance spread, and the shader mirroring v because flipY is off. |
| vitest/jsdom and the WebGL test boundary | F11 | jsdom implements DOM but no WebGL, so R3F is mocked at the Canvas boundary, logic lives below it as pure lib/ functions, and what jsdom cannot see (draw calls, fps, bloom, real context loss) goes on a named runtime checklist. |
| Centreline rebuilt by arc length | F11 | The F04 GLB keeps station i's edges at vertices 2i/2i+1; midpoints rebuild the centreline, and a cumulative arc-length table with binary search gives sampleAt/tangentAt in O(log n) per car per frame, wrap included. |
| Mod-1 unwrap and Fritsch-Carlson interpolation | F11 | Per-lap s_track fractions unwrap to monotone progress via delta − round(delta) + 1 (assumes true advance in 0.5–1.5 laps); Fritsch-Carlson tangent limiting makes the cubic monotone by construction, so an interpolated car never reverses — the reason Catmull-Rom was rejected. |
| WebGL context loss (E-18) | F11 | Browsers reclaim GPU contexts under pressure; preventDefault on webglcontextlost is the contract for restoration, the DOM overlay explains the black canvas from outside it, and the dev overlay can rehearse the loss via WEBGL_lose_context. |
| Frontend provenance ring (5.1 invariant 2) | F11 | Every response passes through one fetch wrapper into a bounded ring (path, status, run/model/config ids, X-Model-Version) before the caller sees it; the backtick overlay renders the ring, so any on-screen number traces to its response. |
| Seeded property loops | F11 | Property-style invariants as plain loops over a mulberry32-seeded generator with the seed printed in every assertion, trading a fast-check dependency for exact replayability — four invariants don't earn a library. |
