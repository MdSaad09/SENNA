# F12 — The energy view and the tyre surface

## What we built and why

F11 gave the dashboard its shell and the first two views: the circuit map and the race
replay. F12 fills the next two, and they are the two a real race engineer opens first.
The energy view answers "did the agent manage the battery well?" — a chart of state of
charge across the whole race, and, under it, how much the car harvested and deployed
each lap. The tyre view answers "how fast is this compound dying?" — a 3D surface of
grip against tyre age, with the failure cliff drawn where the simulator actually snaps
the tyre.

Two design calls run through the whole feature. The first is that these views are
shaped by their question, not by the fact that F11 taught us how to render 3D. Energy
is a thing you read by hovering a lap and comparing bars, so it is a flat 2D chart with
no canvas at all. Grip over age and temperature is a shape you read by orbiting it, so
it is a 3D surface. Correctness over beauty, and the right tool for each.

The second is the F-02 correction, which is the most examinable thing in this feature.
The old spec draft carried a "4 MJ per lap" deployment cap. There is no such cap. The
4 MJ is the size of the battery's usable charge window — you can hold at most 4 MJ of
state of charge — and a car routinely *deploys* more than 4 MJ in a single lap because
it harvests energy mid-lap and spends it again before the lap ends. As of this week that
is not just our reading of the regs, it is verified against the primary source: FIA 2026
Technical Regulations Art 5.4.9 (carried into the consolidated text as Art C5.2.9) caps
the max-minus-min state of charge at 4 MJ, and the old "4 MJ/lap ES-to-MGUK" diagram
label is simply gone from the 2026 text (INDEX.md, AR-04, verified 24 Jul 2026). So the
energy view draws the SOC ceiling at 4 MJ and the per-lap bars against the *harvest*
cap, and it never draws a line at 4 MJ on the deploy bars. A regression test stands
guard over that absence so the deleted deploy plane can never creep back.

The honesty theme from F04 and F11 carries straight through. The tyre surface's
temperature axis is drawn but not fitted — our degradation model is age-only — so the
view says so in words, on the view itself. A compound with no 2026 data of its own
borrows its curve from similar circuits, and the panel names the donors out loud.

## New ideas in this feature

**Matching the tool to the question: 2D charts vs a 3D surface.** F11 was all R3F
because a moving field of cars on a 3D track is inherently 3D. Energy is not. State of
charge over laps is a line; harvest and deploy per lap are paired bars. For that we use
**recharts**, a small React charting library that renders plain SVG: you declare
`<AreaChart>`, `<XAxis>`, `<Bar>` as components and it draws the shapes. No WebGL, no
canvas, no frame loop. `/energy` stays a zero-canvas route (decision 2), which also
keeps the one-canvas invariant (F-28) trivially satisfied. The viva answer: **the energy
story is read by hovering a lap and comparing bars, so it is 2D recharts SVG — a second
WebGL canvas would buy nothing and cost the F-28 one-canvas budget; the tyre view is 3D
because grip over age and temperature is a shape you read by orbiting it (5.10.2 rows 3
and 4).**

**A vertex shader, in plain terms.** The tyre surface is a flat grid of points, and each
point has to be lifted to a height equal to the grip at that (age, temperature). Doing
that lift on the CPU, for thousands of points, every frame, would be wasteful. A
**vertex shader** is a tiny program that runs on the GPU, once per grid point ("vertex"),
in parallel, and its job is to decide where that vertex ends up on screen. Ours reads
the vertex's grid position, computes `grip = 1 - a*age^b`, and moves the vertex up by
that grip. It is written in GLSL, the GPU's own C-like language. The inputs it can't
compute itself — the fitted `a` and `b`, the axis bounds — are passed in as **uniforms**
(one value shared by every vertex), and a value the vertex computes for the fragment
stage to colour with is passed along as a **varying**. Mental model: instead of a person
placing 2,000 pins on a board one at a time, you hand 2,000 pins the same short
instruction and they all place themselves at once.

**The shader's pure-TS twin.** A shader can't be unit-tested. jsdom has no GPU (the
lesson from F11), so the GLSL never runs in the test suite, which means the surface's
core equation would be untested — and that equation *is* the physics of the view. The
fix is the pattern F11 used for ribbon strips, applied here deliberately:
`src/lib/gripSurface.ts` is a plain-TypeScript twin of the shader. Same formula, same
constants, testable directly. The shader mirrors the twin line for line, and one test
pins the contract that matters: at the 30 C reference slice the twin must equal the
served fitted curve `1 - a*age^b` exactly. The twin is the source of truth; the shader
is its GPU copy. The viva answer: **the surface's grip equation can't be tested through
jsdom because the shader never runs there, so the equation lives in a pure-TS twin the
tests pin, and the GLSL is written to mirror it; they are forced to agree at the fitted
30 C slice, which is the only slice any readout is allowed to use (E-09, decision 1).**

**F-02: the usable SOC window is not a per-lap deploy cap.** Covered above; it earns a
ledger row because it is the single easiest physics regression to make and the one most
likely to be probed in the viva. Four things follow from it in the code: the SOC axis
tops out at 4 MJ (the store), the deploy bars have *no* ceiling line, the harvest bars
carry the per-circuit harvest cap (8.5 MJ baseline, `h_max_mj`, E-02), and a test counts
the reference lines on the bars panel to keep it that way.

**Render the fit, not the raw data (E-09).** The tyre view never fetches a single lap of
telemetry. It draws the fitted power-law curve and nothing else — `a`, `b`, the support
columns, the confidence flag. A test asserts, via the provenance ring, that no `/frames`
or `/energy` request ever fires while the tyre view is open. Showing raw scatter would
invite the eye to read noise as signal; showing the fit, labelled with its confidence,
is the honest thing (T5, 5.10.2 row 4).

**One rule, two callers: `cliff_age_laps`.** The simulator fails a tyre when its age
passes a fixed margin beyond the compound's fitted `max_age_seen`. The tyre view wants
to draw that exact cliff. Rather than let the API invent its own number, the rule is
extracted into one function that both the env and the `/tyres` endpoint call. The API
draws the cliff the sim enforces because it is literally the same line of code (F10's
"one card pipeline, two callers" idea, again).

Reused from earlier lessons and only name-checked here: react-query server state and
`staleTime: Infinity` on finished runs (F11), the stylised-vs-sourced provenance rule
for pixels (F04, F-12), the frontend provenance ring (F11), Pydantic response models as
the 5.9.2 contract (F10), the vitest/jsdom WebGL boundary and pure-`lib/` logic (F11),
seeded property loops with a printed seed (F11), and config provenance (F00).

## The code, guided

Reading order follows one question each: the backend that serves the two shapes, then
the frontend that draws them, then the tests that were written first.

### api/schemas.py — four additive fields, recorded as a divergence

The energy and tyre endpoints already existed from F10; F12 sharpens their shapes. The
`EnergyProfile.laps` field was a bare `list`; it is now a typed `EnergyLap`, and three
scalar fields are added. This is a 5.9.2 shape change, so it is recorded as a divergence
the same way F10 and F11 recorded theirs (the file's header docstring says so). All four
are *additive* — nothing renamed or removed — so no existing consumer breaks. The two
fields that carry the feature's meaning:

```python
class EnergyLap(BaseModel):
    lap: int
    harvest_mj: float
    deploy_mj: float
    soc_mj: float                 # clipped to [0, usable_soc_mj] in the sim (E-01)
    mode: int                     # 0-3: conserve, balanced, attack, defend
    pit: int                      # 0 = stayed out; 1-5 = pitted for compound code + 1
```

```python
class EnergyProfile(BaseModel):
    ...
    usable_soc_mj: float          # the 4 MJ store, so the SOC axis is served not hardcoded
```

`usable_soc_mj` exists so the frontend never types `4`. The number the SOC axis tops out
at is served from `physics_2026.yaml` (`usable_capacity_mj: 4.0`, sourced AR-04), which
means the anti-black-box contract reaches all the way to an axis label. On
`DegradationCurve`, `source_circuit` (the T5 donor list, `None` for a direct fit) and
`cliff_age` (the sim's failure boundary) are the other two additions.

### senna/env/scenario.py — the cliff rule, extracted

This is the whole "one rule, two callers" idea in one function, so it earns line-level
attention.

```python
def cliff_age_laps(max_age_seen: int | None, env_cfg: dict) -> int:
    horizon = env_cfg["obs"]["tyre_age_norm_laps"]
    margin = env_cfg["tyre_failure"]["cliff_age_margin_laps"]
    base = horizon if max_age_seen is None else max_age_seen
    return int(base) + int(margin)
```

Line 1 reads the observation horizon (`tyre_age_norm_laps: 40`) — the age at which the
normalised tyre-age observation hits 1.0. Line 2 reads the failure margin
(`cliff_age_margin_laps: 3`) — how many laps past a compound's fitted support the sim
will let a tyre run before it snaps. Line 3 is the fallback: a cluster-transfer curve
never observed its own tyre wearing out, so `max_age_seen` is `None`, and the cliff falls
back to the 40-lap horizon — the same fallback `build_scenario` uses for `deg_max_age`
just below in this file, so the view and the sim agree even for borrowed curves. Line 4
adds them. Both numbers live in `configs/env.yaml`, the file `race_env.py` reads to
enforce the cliff, so there is no literal anywhere in the chain. The viva answer: **the
served cliff age is computed by the same function the env uses to fail a tyre, so View 4
draws the exact boundary the agent raced into rather than a number of its own — a
transfer fit with no observed cliff falls back to the tyre-age horizon, matching the
sim's own fallback (E-09).**

`tests/env/test_scenario.py` pins both branches against the config values, never against
literals: a direct fit that saw age 30 cliffs at `30 + margin`, a transfer cliffs at
`fallback + margin`, and a second test walks several ages asserting the served cliff
equals `max_age + margin` — the boundary `race_env.py:429` enforces.

### api/routes/energy.py — the ledger, replayed from stored frames

Block-level, because it is a read: fetch every stored `LapFrameRow` for the run in lap
order, and project each frame into an `EnergyLap`. Two lines carry the interpretability
weight:

```python
        h_max_mj=config.load("circuits")[row.circuit]["h_max_mj"],
        usable_soc_mj=config.load("physics_2026")["energy_store"]["usable_capacity_mj"],
```

The harvest cap comes from the per-circuit `circuits.yaml` entry (E-02 — the ceiling the
race was actually run under), and the SOC store from `physics_2026.yaml`. Both are served
so the frontend can stay dumb. The per-lap projection reads `mode` and the pit action
straight out of the agent's recorded frame:

```python
                mode=frame["agent"]["mode"],
                pit=frame["agent"]["action"]["pit"],
```

Old stored runs already carry `mode` and the pit action in every frame, which is why the
plan noted "no migration" — the fields were always there, F12 just names them in the
response.

### api/routes/tyres.py — the fitted surfaces, verbatim

Also a read: pull the fitted `degradation` block for the circuit (404 if it has none —
`french_grand_prix` is the standing example), and mirror each `(era, compound)` fit into
a `DegradationCurve`. The one computed field is the cliff:

```python
            source_circuit=params.get("source_circuit"),
            cliff_age=cliff_age_laps(params.get("max_age_seen"), env_cfg),
```

`source_circuit` survives the trip untouched so the dashboard can name the donors;
`cliff_age` calls the shared rule. Everything else — `a`, `b`, `low_confidence`,
`max_age_seen`, `n_laps` — is copied through verbatim, honesty flags included. A T5
cluster transfer says it is low-confidence, and the flag must reach the screen intact.

### src/lib/gripSurface.ts — the equation, in testable TypeScript

This is the twin the shader mirrors, and the surface's physics, so it gets line-level
treatment.

```ts
export function fittedGrip(a: number, b: number, age: number): number {
  return clamp01(1 - a * age ** b);
}
```

The served power law, `grip(age) = 1 - a*age^b`, clipped to [0, 1] exactly as the sim's
`grip_est` does (T5). This is the *only* function whose numbers a hover or readout is
allowed to touch, because it is the fitted 30 C slice — the only slice the model actually
fits.

```ts
export function tempGripFactor(tempC: number): number {
  const span = Math.max(
    TYRE_TEMP_REF_C - TYRE_TEMP_AXIS_MIN_C,
    TYRE_TEMP_AXIS_MAX_C - TYRE_TEMP_REF_C,
  );
  const distance = Math.abs(tempC - TYRE_TEMP_REF_C) / span;
  return 1 - TYRE_TEMP_GRIP_PENALTY * distance * distance;
}
```

The stylised temperature response. Read it carefully, because its honesty is in its
shape. At the reference temperature (30 C) `distance` is 0, so the factor is exactly 1 —
the surface *equals* the fitted curve on that slice, and no numeric readout can drift.
Away from 30 C the factor dips, at most `TYRE_TEMP_GRIP_PENALTY` (0.08) at the axis
extremes, as a gentle parabola. The dip is deliberately understated because it is not a
prediction; it is relief on a surface so the 3D shape reads as a surface and not a
ruled sheet. The view carries the words that make this honest (see below). The viva
answer: **the fit is age-only (T5), so the temperature axis is a stylised illustration
that dips grip by at most 0.08 for shape and is exactly 1.0 at the 30 C reference, and
the view labels it "not fitted, not a prediction" on the view itself — every hover number
comes off the reference slice only, so nothing numeric ever reads off the stylised
dimension (decision 1).**

```ts
export function surfaceGrip(a: number, b: number, age: number, tempC: number): number {
  return clamp01(fittedGrip(a, b, age) * tempGripFactor(tempC));
}
```

The full surface height is the fitted grip scaled by the temperature factor, re-clipped.
Because `tempGripFactor(30) === 1`, `surfaceGrip(a, b, age, 30) === fittedGrip(a, b, age)`
— the property the test names "at the reference temperature the surface equals the fitted
curve exactly."

`buildGripSurface` (block-level) lays out the flat unit grid the shader will lift: a
`GRIP_AGE_SAMPLES × GRIP_TEMP_SAMPLES` mesh of vertices at `(x, y) = (age fraction,
temperature fraction)`, plus the triangle indices that stitch them. `ageMax` is set to
the served `cliff_age`, so the age axis runs to exactly where the sim fails the tyre.

### src/views/tyres/GripSurface.tsx — the same maths, on the GPU

The shader is the twin's mirror. The vertex program, line by line:

```glsl
    float age = position.x * uAgeMax;
    float temp = mix(uTempMin, uTempMax, position.y);
    float fitted = clamp(1.0 - uA * pow(max(age, 0.0), uB), 0.0, 1.0);
    float span = max(uTempRef - uTempMin, uTempMax - uTempRef);
    float d = abs(temp - uTempRef) / span;
    float grip = clamp(fitted * (1.0 - uTempPenalty * d * d), 0.0, 1.0);
    vGrip = grip;
    vAgeFrac = position.x;
    vec3 lifted = vec3(position.x, position.y, grip * uHeight);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(lifted, 1.0);
```

Line 1 turns the vertex's x (a 0..1 age fraction) into a real age by scaling to
`uAgeMax`, the served cliff. Line 2 turns its y into a real temperature by interpolating
between the axis bounds. Line 3 is `fittedGrip` in GLSL — the same `1 - a*age^b`, clipped,
`max(age, 0)` guarding `pow` against a negative base. Lines 4–6 are `tempGripFactor`
times the fitted grip: identical arithmetic to the twin, which is the whole point.
`vGrip` and `vAgeFrac` are the *varyings* handed to the fragment shader for colouring.
The last two lines lift the vertex to height `grip * uHeight` and project it to the
screen. Every `u`-prefixed name is a *uniform* set from the served curve on the JS side:

```tsx
      uniforms: {
        uA: { value: curve.a },
        uB: { value: curve.b },
        uAgeMax: { value: curve.cliff_age },
        ...
```

So the fitted `a` and `b` cross from the API response into GPU memory here, once per
compound. The fragment shader (block-level) colours by grip, green to red, and washes the
zone past the fitted support toward amber so a stint stretched past where the data
supports it reads as a warning:

```glsl
    float beyond = step(uSupportFrac, vAgeFrac);
    vec3 colour = mix(gripColour, uCliffTint, beyond * uExtrapolationWash);
```

`step` returns 1 once the age fraction passes `uSupportFrac` — the fraction of the axis
that the compound's real `max_age_seen` covers. On the JS side, a transfer with no
observed support gets `supportFrac = 0`, so its whole surface washes amber, matching its
low-confidence flag. The geometry and material are built imperatively with `useMemo`, so
a `useEffect` cleanup disposes both GPU buffers when the compound changes or the route
unmounts — the same "geometry we built, we dispose" rule F11 established.

### src/views/tyres/TyreSurfaceView.tsx and FitPanel.tsx — the honesty, on screen

`TyreSurfaceView` is block-level plumbing: circuit / era / compound selectors gated on
`coverage.deg_fit`, one `CanvasHost` with one `GripSurface`, `OrbitControls` so you can
turn it, and an honest empty state on 404. The two paragraphs that carry the contract are
the axis caption and the label the plan calls unmissable:

```tsx
            {/* decision 1: the fit is age-only, so the temperature axis is illustration */}
            <p className="mt-1 text-neutral-500">
              temperature response — stylised illustration, not fitted, not a prediction; the
              T5 fit is age-only
            </p>
```

It sits on the view, not in a tooltip, because a caveat you have to hover for is a caveat
you can hide. `FitPanel` states the fit in words and keys its confidence line on
*mechanism*, not on the flag alone:

```tsx
function confidence(curve: DegradationCurve): string {
  if (curve.source_circuit !== null) {
    const donors = curve.source_circuit.split(",").map(...).join(", ");
    return `cluster transfer (T5) — from ${donors}`;
  }
  if (curve.low_confidence) {
    return `thin fit — low confidence (n=${curve.n_laps ?? "?"}, ...)`;
  }
  return "direct fit — high confidence";
}
```

The subtlety: a thin 2024 direct fit *also* carries `low_confidence`, so the flag alone
can't tell a borrowed curve from a thin one. The discriminator is `source_circuit` — its
presence means "these numbers came from other circuits, here they are." A cluster
transfer names its donors; a thin fit admits it is thin. Neither hides.

### src/views/energy/ — the F-02 tripwire, drawn from one array

`EnergyView` is block-level: read `?run=` off the URL, poll the run until `complete`
(react-query), and only then fetch the energy profile. In-flight runs show status, never
an empty chart (E-16). `SocPanel` draws the SOC ribbon with its axis bounded by the
*served* store:

```tsx
            <YAxis domain={[0, profile.usable_soc_mj]} stroke="#737373" fontSize={11} />
```

The axis top is `profile.usable_soc_mj`, never a literal `4`. That is the whole "every
number came from the API" discipline in one line — change the store in `physics_2026.yaml`
and the axis follows. Pit laps are marked from the recorded `pit` action so a stint's
energy story lines up with its strategy.

`EnergyBarsPanel` is where F-02 lives, and the design is worth the line-level read:

```tsx
  const referenceLines = [{ key: "harvest-cap", mj: profile.h_max_mj, label: "harvest cap" }];
```

Every reference line on the bars chart goes through this one array. There is exactly one
entry, and it is the served harvest cap — not the fictional 4 MJ deploy plane, which does
not exist. The array feeds *two* things: the drawn `<ReferenceLine>` on the chart, and an
accessible list below it:

```tsx
      <ul data-testid="bars-reference-lines" className="mt-1 text-xs text-neutral-500">
        {referenceLines.map((line) => (
          <li key={line.key} data-mj={line.mj}>
            {line.label} {line.mj} MJ per lap
          </li>
        ))}
      </ul>
```

This list is not decoration. recharts draws SVG, and jsdom can't see SVG (the F11 test
boundary), so a test can't read the drawn line. The `<ul>` is the same data in DOM the
test *can* read, which is why it exists — and because both the chart and the list map the
same `referenceLines`, they can never disagree. The regression test in
`EnergyView.test.tsx` reads this list, asserts it has exactly one item, asserts that item
is the 8.5 MJ harvest cap, and asserts nothing in the panel says "4 MJ" or "deploy cap."
If a future edit reintroduced a deploy plane, it would have to appear in this array, where
the test counts and reads it. The viva answer: **per-lap deployment routinely exceeds
4 MJ because the car harvests mid-lap, so the bars panel draws no deploy ceiling at all —
its only reference line is the per-circuit harvest cap (E-02), and a regression test
reads an accessible list of the panel's reference lines to keep the removed 4 MJ deploy
plane out for good (F-02, R-03).** The comment above the array names it a tripwire, which
is exactly what it is.

### The tests that came first

`gripSurface.test.ts` pins the twin: `tempGripFactor(30)` is exactly 1, the surface
equals the fitted curve at 30 C across several ages, and a seeded property loop (mulberry32,
seed printed, F11's pattern) proves grip is bounded in [0, 1] and non-increasing in age
across the whole `fits.yaml` parameter box `a ∈ [0, 5] × b ∈ [0.3, 3]`. That property is
the shader's correctness too, by the twin contract. `EnergyView.test.tsx` is the F-02
tripwire described above, plus the served-axis, footer, pit-mark and in-flight checks.
`TyreSurfaceView.test.tsx` asserts, through the provenance ring, that opening the view
fetches `/v1/tyres` and never `/frames` or `/energy` — the E-09 "render the fit, not the
data" property made observable. `routeMount.test.tsx` gains the two new routes with their
canvas counts (`/energy 0`, `/tyres 1`) and keeps the MutationObserver peak at 1, so the
one-canvas invariant (F-28) still holds with four real views mounted. And the backend
tests assert the cliff rule and the donor string against config values, no literals.

## How it connects

```
 browser
 ┌─ shell (F11): routes.tsx — /circuit /replay now joined by /energy /tyres ──────┐
 │   /energy  ── recharts SVG, NO canvas ── SocPanel + EnergyBarsPanel            │
 │              axis top = served usable_soc_mj · bars ref line = served h_max    │
 │   /tyres   ── CanvasHost ── GripSurface (vertex shader) + FitPanel             │
 │              shader mirrors lib/gripSurface.ts · temp axis labelled stylised   │
 └───────────┬─────────────────────────────────────────────────────────────────────┘
             │ api/client.ts → provenance ring (E-09 tyre test reads it)
             ▼
 F10 API: GET /v1/energy/{run}  ── EnergyLap[] from stored frames + usable_soc_mj
          GET /v1/tyres/{slug}  ── DegradationCurve[] + cliff_age + source_circuit
                                        │
                                        └── cliff_age_laps(...)  ◄── same function
 senna/env/scenario.py ──────────────────────────────────────────  the sim calls
      (one rule, two callers: the API draws the cliff the env enforces)
```

F10 built both endpoints; F12 gave them four fields and two views. F13 brings the live
WebSocket view and the counterfactual, reusing this same shell and the RunPicker this
feature generalised out of the replay view.

## Try it yourself

All frontend commands from `frontend/`; Python from the repo root.

1. **Read the two views against their data.** `docker compose up --build`, open
   `http://localhost:5173`. Start a run from the energy view, wait for the poll to flip,
   and read the SOC axis top against `configs/physics_2026.yaml` `usable_capacity_mj` —
   they must match. Then press backtick and find the `/v1/energy/...` response the chart
   came from. Go to the tyre view, orbit the surface, switch compounds, and read the fit
   panel's confidence line. You'll know it worked when you can point at the SOC axis top
   and the harvest-cap line and name the served field each came from.

2. **Break the F-02 tripwire.** In `EnergyBarsPanel.tsx`, add a second entry to
   `referenceLines`: `{ key: "deploy-cap", mj: 4, label: "deploy cap" }`. Run
   `npm test -- EnergyView`. You'll know it worked when the "no 4 MJ cap marker (F-02)"
   test fails on the length assertion (it now sees two lines, not one) and on the
   `queryByText(/4\s*MJ/i)` absence check. Revert, and note that this is exactly the
   regression the test exists to catch.

3. **Prove the twin and the shader must agree.** In `lib/gripSurface.ts`, change
   `tempGripFactor` to return `1 - TYRE_TEMP_GRIP_PENALTY * distance` (drop one
   `* distance`, making the dip linear instead of parabolic). Run
   `npm test -- gripSurface`. The "equals the fitted curve at the reference" test still
   passes (the factor is still 1 at 30 C), but think about what you just did: the twin no
   longer matches the GLSL in `GripSurface.tsx`, and no test can catch that drift because
   the shader can't run under jsdom. You'll know it worked when the suite is green *and*
   you can explain why that green is a warning, not a reassurance — the twin and the
   shader are kept in sync by discipline, not by the test runner. Revert both.

4. **Change the cliff margin and watch it flow.** In `configs/env.yaml`, set
   `cliff_age_margin_laps` from 3 to 6. Run
   `python -m pytest tests/env/test_scenario.py -q`. You'll know it worked when both
   cliff tests fail with the served cliff now `max_age + 6`, and you can say in one
   sentence why the tyre view's drawn cliff would move by the same 3 laps without
   touching any frontend code — one rule, two callers. Revert.

5. **Give the tyre view a circuit with no fits.** Navigate to
   `/tyres?circuit=french_grand_prix`. You'll know it worked when you get the honest
   "no degradation fits" empty state instead of a broken surface, and you can trace it to
   the API's 404 and the `retry: false` on `useDegradationCurves` (a 404 is an answer, not
   a flake).

## Check yourself

1. Why is the energy view 2D recharts while the tyre view is 3D R3F? Defend the split.

2. Someone claims the deploy bars should be capped at 4 MJ because "the battery is 4 MJ."
   Correct them, and say what the 4 MJ actually is and where it *does* appear in the view.

3. What is a vertex shader, and why does the tyre surface use one? Why is there a pure-TS
   twin of it, and what exactly must the two agree on?

4. The tyre view's temperature axis is drawn but not fitted. How does the code keep that
   honest — both visually and numerically?

5. `cliff_age_laps` lives in `senna/env/scenario.py`, not in the API. Defend that. What
   would go wrong if the `/tyres` endpoint computed the cliff itself?

---

### Answers

1. Energy is a thing you read by hovering a lap and comparing bars — state of charge over
   laps, harvest and deploy per lap — which is a flat 2D chart, so it uses recharts SVG
   with no canvas, and `/energy` stays a zero-canvas route (decision 2). Grip over age and
   temperature is a shape you read by orbiting it, which is inherently 3D, so the tyre view
   uses an R3F canvas with a vertex-shaded surface. A second WebGL canvas for the energy
   view would add cost against the F-28 one-canvas budget and buy nothing; matching the
   tool to the question is the point (5.10.2 rows 3 and 4).

2. The 4 MJ is the size of the battery's usable state-of-charge window — the max-minus-min
   SOC may not exceed 4 MJ (FIA Art 5.4.9 / C5.2.9, verified) — not a limit on how much
   energy the car may deploy in a lap. A car harvests energy mid-lap under braking and
   spends it again, so per-lap deployment routinely exceeds 4 MJ; the old "4 MJ/lap" cap
   was a fiction removed in v3 (F-02, R-03). The 4 MJ appears in the view as the *SOC* axis
   ceiling (served as `usable_soc_mj`, E-01), and the deploy bars carry no ceiling at all —
   the only reference line on the bars panel is the per-circuit harvest cap (E-02).

3. A vertex shader is a small GPU program that runs once per grid vertex in parallel and
   decides where that vertex lands; ours lifts each grid point to a height equal to
   `grip = 1 - a*age^b`, which is far cheaper than lifting thousands of points on the CPU
   every frame. It can't be unit-tested because jsdom has no GPU, so the equation lives in
   a pure-TypeScript twin (`lib/gripSurface.ts`) that the tests pin, and the GLSL is
   written to mirror it. They must agree exactly at the 30 C reference slice — the only
   slice the fit actually models — because that is the slice every hover and readout number
   reads off (E-09, decision 1).

4. Visually: the view carries an unmissable label on the view itself (not a tooltip) that
   reads "temperature response — stylised illustration, not fitted, not a prediction; the
   T5 fit is age-only." Numerically: the stylised temperature factor is exactly 1.0 at the
   30 C reference, so the surface *equals* the fitted curve on that slice, and every readout
   is taken from that slice only — nothing numeric is ever read off the stylised
   temperature dimension. The dip away from 30 C is capped at 0.08 and exists only so the
   3D shape reads as a surface (decision 1).

5. The simulator already fails a tyre at a fixed margin past its fitted support, and the
   view's whole promise is to draw the cliff the agent actually raced into — so the rule
   must be the single source both call, not two implementations free to drift. If the API
   recomputed it, a later change to the env's margin (in `configs/env.yaml`) would move the
   real cliff while the drawn cliff stayed put, and the view would quietly lie. Extracting
   `cliff_age_laps` means the endpoint draws the exact boundary `race_env.py` enforces,
   pinned by a test that asserts the served cliff against the config values (E-09).

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| Matching the tool to the question (2D chart vs 3D surface) | F12 | Energy is read by hovering a lap, so it is recharts SVG on a zero-canvas route; grip over age is a shape you orbit, so it is a vertex-shaded R3F surface — a second canvas would cost the F-28 budget and buy nothing (5.10.2 rows 3-4). |
| Vertex shader (GPU per-vertex program) | F12 | A small GLSL program run once per grid vertex in parallel that positions it; the tyre surface lifts each vertex to grip = 1 − a·age^b, with fitted a/b passed as uniforms and grip handed to the fragment stage as a varying. |
| Shader ↔ pure-TS twin | F12 | The shader can't run under jsdom, so its equation lives in a testable TS twin (lib/gripSurface.ts) the tests pin, and the GLSL mirrors it; they are forced to agree at the fitted 30 C slice, the only slice a readout may use (E-09). |
| F-02: usable SOC window, not a per-lap deploy cap | F12 | The 4 MJ is the battery's max−min SOC window (FIA Art 5.4.9 / C5.2.9, verified AR-04), not a deploy limit; per-lap deploy exceeds it because the car harvests mid-lap, so the bars panel draws only the harvest cap and a reference-line list keeps the removed deploy plane out (R-03). |
| Render the fit, not the raw data (E-09) | F12 | The tyre view fetches no telemetry — it draws the fitted power law with its confidence flag, and a provenance-ring test proves no /frames or /energy call fires; a stylised, labelled temperature axis stands in for the term the age-only fit lacks (T5). |
| One rule, two callers (cliff_age_laps) | F12 | The tyre-failure cliff is one function in scenario.py that both the env and the /tyres endpoint call, so the view draws the exact boundary race_env.py enforces rather than a literal of its own. |
