# F04 — Circuit ribbon pipeline

## What we built and why

Every view in the dashboard eventually draws a track. The car has to sit on something,
the pit stops have to happen somewhere, the energy zones have to light up along a real
shape. F04 builds that shape: one 3D track ribbon per circuit, saved as a file the
browser can load directly.

We do not have official CAD models of the circuits, and we would not want to hand-draw
22 of them. What we do have, from F01, is GPS telemetry — the position of the car,
lap by lap, sampled many times a second. So the plan is to take the fastest clean lap
ever driven at a circuit and treat the path the car traced as the centreline of the
track. Widen that line into a 12 m strip, give it a bit of fake elevation so it reads as
three-dimensional, mark the corners and braking zones, and export the whole thing.

The catch is that raw GPS is a mess. It jitters, it has the occasional teleport, and a
racing line through a hairpin can be tighter than the track is wide. If you naively push
a 12 m ribbon along a 5 m radius corner, the inside edge of the ribbon crosses over
itself and the track folds inside-out. Monaco and Hungary do this. So most of the work
in F04 is geometry that keeps the ribbon clean: resample the line to even spacing, smooth
out the jitter, carry a stable "which way is sideways" direction around the loop without
it flipping, and clamp the ribbon narrower than any corner it is going through. The spec
lays this out as seven steps (5.10.1), and the code follows them in order.

One rule underpins the whole feature: elevation and banking are decoration, never data
(F-12). The Z channel in GPS is noisy and sometimes missing entirely, and nothing in the
race simulation depends on how hilly the track looks. So we exaggerate it for the eye and
label every such choice "stylised" in the metadata, so the UI can be honest about what is
measured and what is invented.

## New ideas in this feature

**GLTF / GLB — a mesh is positions plus indices.** A 3D model, at bottom, is two lists.
One is a flat array of vertex positions: x, y, z, x, y, z, and so on. The other is a list
of triangles, where each triangle is three integers that index into the position list.
The renderer draws a filled triangle for every triple. glTF is the standard file format
for exactly this (think "JPEG for 3D"), and GLB is its single-file binary form, where the
JSON structure and the raw number buffer live in one file. SENNA uses GLB because the
frontend (R3F, in F11) loads it natively, and one self-contained file per circuit is easy
to serve and cache (5.10.1 item 7). Mental model: the positions are dots in space, the
indices are the join-the-dots instructions, and a triangle is the smallest thing you can
paint a colour on.

**Arc-length resampling.** GPS samples land at even *time* intervals, which means they
bunch up where the car was slow and spread out where it was fast. For geometry we want the
opposite: points evenly spaced along the *track*, so a corner has as many points per metre
as a straight. Arc-length resampling walks the cumulative distance along the path and
drops a fresh point every 2 metres, interpolating between the original samples. SENNA
needs it (5.10.1 item 2) because every step after this — smoothing, curvature, the
ribbon width clamp — assumes uniform spacing to behave. Smallest example: a path that
goes 0 m, 1 m, 5 m, 6 m gets resampled at 0, 2, 4, 6, and the middle points are found by
linear interpolation.

**Savitzky-Golay smoothing.** A smoothing filter that slides a small window along the
data and, instead of just averaging, fits a low-order polynomial to each window and takes
that polynomial's value at the centre. The payoff over a plain moving average is that it
keeps the *shape* of a bend — a cubic can follow the curve of a corner while still killing
the high-frequency GPS noise. SENNA smooths the plan (X, Y) with a short window and the
elevation (Z) with a much wider one, because Z is far noisier (5.10.1 item 2). Mental
model: a moving average flattens a hill; Savitzky-Golay traces a smooth line *over* the
hill.

**Frenet vs rotation-minimising frames.** To turn a line into a ribbon you need, at every
point, a "sideways" direction to push the two edges out along. The textbook choice is the
Frenet frame, built from the curve's own acceleration — but it has a fatal flaw for us: at
an inflection point or a hairpin, where the curve momentarily straightens and then bends
the other way, the Frenet normal *flips 180 degrees*. Push a ribbon edge along a
direction that suddenly flips and the ribbon turns inside-out. A rotation-minimising frame
(RMF) avoids this by *carrying* a sideways vector along the curve, rotating it as little as
each step demands, never letting the curve's own wiggles snap it around. SENNA uses RMF
via parallel transport precisely to kill this flip (E-17). The analogy: walk a corridor
holding a spirit level flat and only tilting it when the floor forces you to, versus
re-deriving "level" from scratch at every step and getting it upside-down on the stairs.

**Parallel transport and holonomy.** Parallel transport is the specific trick that carries
the sideways vector forward: at each step you reflect the frame twice (a "double
reflection") so it lands on the next segment with minimal turn. On a closed loop there is a
subtlety — you can transport a vector all the way around a circuit and find it does *not*
come back to itself. The leftover rotation is called the holonomy angle. SENNA measures
that residual twist and spreads it back evenly over all the points, so the frame is
perfectly periodic and the start-finish quad has no visible seam. Smallest example of
holonomy: carry a "pointing forward" arrow around a triangular walk on a globe and it comes
back rotated — the surface curved, so the frame picked up an angle.

**Menger curvature and radius of curvature.** How tight is the track right here? Take three
consecutive points; there is exactly one circle through them. Its radius is the local
radius of curvature — huge on a straight, small in a hairpin. Menger's formula computes that
radius from the three points as (side_a · side_b · side_c) / (4 · triangle_area). SENNA
computes it (5.10.1 item 4) so it can clamp the ribbon's half-width to stay below the local
radius, which is what stops tight corners from folding. Mental model: the radius of the
biggest circle that snugly kisses the track at that point.

**Segment-intersection orientation test.** To *prove* a ribbon edge never crosses itself,
we need to test whether two line segments intersect. The clean way uses orientation: three
points are either a left turn, a right turn, or straight, given by the sign of a small
cross-product. Two segments properly cross only if each one's endpoints straddle the other
— they sit on opposite sides. SENNA runs this over every edge (E-17) as the ultimate check
that the geometry is valid. Smallest example: segment AB and segment CD cross only if C and
D are on opposite sides of line AB *and* A and B are on opposite sides of line CD.

**Stylised vs sourced provenance for visual data (F-12).** The project's anti-black-box
rule, applied to pixels. A number that affects the physics carries a `sourced` or `fitted`
provenance. A number that only affects how the track *looks* — elevation exaggeration,
camber, ribbon width — is marked `stylised`, both in the config comment and in the exported
metadata. SENNA does this so the dashboard can put "elevation: stylised" in its legend and
never let a viewer mistake decoration for measurement.

## The code, guided

Everything lives under `senna/circuits/`. Reading order: how a lap is chosen and loaded,
then the pure-geometry core, then elevation, annotations, export, and the orchestrator that
strings them together.

### sources.py and the loader — picking the lap

`pick_most_recent_dry` (`sources.py:10`) is four lines. Given the sessions ingested for one
event, keep only the dry ones (`is_dry` is the flag F01 computed at ingest), and return the
latest by UTC date. Dry so the racing line is the real line and not a wet-weather detour;
most recent so the ribbon matches the current layout. If every session ran wet it returns
`None`, and the build skips that circuit rather than draw a rain line.

The actual telemetry read is `load_fastest_lap_geometry` in `fastf1_loader.py:81`, the one
place in the package allowed to import fastf1. The load-bearing line (`fastf1_loader.py:95`):

```python
lap = session.laps.pick_accurate().pick_fastest()
```

`pick_accurate()` first, `pick_fastest()` second, and the order matters. `pick_accurate`
drops laps FastF1 flags as untrustworthy (bad timing, in/out laps); `pick_fastest` then
takes the quickest of what survives. Then the centreline runs through F01's `clean_pos_data`
(`fastf1_loader.py:97`) — decimetres to metres, OnTrack points only, a z-score gate on
point-to-point speed. Picking an accurate lap and *then* cleaning it is a deliberate double
guard: a track-limits excursion or a GPS teleport must not reach the geometry, because a
data spike there would look exactly like a real self-intersection (E-17). Speed, throttle,
and distance ride the separate car-data channel for the annotations, and corners come from
`get_circuit_info()`. Note the loader returns plain numpy arrays in a dict — the pandas
stays behind this boundary, per the package rule.

### geometry.py — the pure-numpy core

This is the heart of F04, and it is deliberately pure: numpy in, numpy out, no FastF1, no
pandas, no I/O. That is what lets the tests throw synthetic hairpins at it and trust the
result.

`resample_by_arc_length` (`geometry.py:14`) is the even-spacing step:

```python
step = np.linalg.norm(np.diff(points, axis=0), axis=1)
arc = np.concatenate([[0.0], np.cumsum(step)])
targets = np.arange(0.0, arc[-1], spacing_m)
return np.column_stack([np.interp(targets, arc, points[:, axis]) for axis in range(3)])
```

Line one: the straight-line distance between each consecutive pair of raw points. Line two:
cumulative sum, so `arc[k]` is the distance travelled to reach point k — the odometer. Line
three: the new stations we want, every 2 m from zero up to the total. Line four: for each
axis, look up where those even-distance targets fall on the odometer and linearly
interpolate the coordinate. The result is the same path, re-dotted at uniform spacing.

`savgol_smooth` (`geometry.py:29`) wraps scipy's `savgol_filter` with one important choice —
the `mode` (`geometry.py:33`):

```python
mode = "wrap" if closed else "interp"
```

On a closed loop the filter window at the start-finish line must see the *other* end of the
lap, not fall off an edge; `"wrap"` makes the data periodic so the smoothing is seamless
across the seam. An open lap uses `"interp"`, which fits the ends without wrapping. The
build passes the plan a short window and the elevation a wide one, which is where "Z smoothed
harder" actually happens.

`rotation_minimising_frames` (`geometry.py:37`) is the twist-free sideways direction, and it
is the most subtle function in the feature. First the tangents (`geometry.py:49`) — the
forward direction at each point — using a periodic central difference on a closed loop so the
seam tangent is not one-sided. Then it seeds a normal orthogonal to the first tangent and
walks it forward (`geometry.py:52-55`):

```python
for i in range(len(points) - 1):
    normals[i + 1] = _transport(
        normals[i], tangents[i], tangents[i + 1], points[i + 1] - points[i]
    )
```

Each step *transports* the current normal onto the next segment with the least rotation.
`_transport` (`geometry.py:166`) is the double reflection from Wang et al. 2008: reflect the
frame across the step vector, then reflect again across the bisector that maps the old
tangent onto the new one. Two reflections compose into the minimal rotation, no trig
required.

Then the closed-loop correction (`geometry.py:58-63`):

```python
if closed:
    wrapped = _transport(normals[-1], tangents[-1], tangents[0], points[0] - points[-1])
    holonomy = _signed_angle(wrapped, normals[0], tangents[0])
    spread = holonomy * np.arange(len(points)) / len(points)
    turned = [_rotate_about(n, t, a) for n, t, a in zip(normals, tangents, spread, strict=True)]
    normals = _unit(np.array(turned))
```

Transport the last normal one more step back onto the first segment. Compare where it lands
to the actual first normal: the angle between them is the holonomy, the accumulated twist
around the loop. Spread that angle linearly over all stations (a little back-rotation at
each) so the frame closes on itself exactly. Without this the start-finish quad would carry
the entire twist in one jump and show a seam. The test `test_rmf_is_periodic_on_a_closed_loop`
pins it: every step including the wrap has a normal-to-normal dot above 0.99. And
`test_rmf_no_twist_flip_across_hairpin` proves it is needed at all — it computes the naive
Frenet normal in the test itself, shows it flips sign at the inflection, and asserts RMF does
not.

`curve_radius` (`geometry.py:69`) is Menger curvature, vectorised over all points at once:

```python
side_a = np.linalg.norm(points - before, axis=1)
side_b = np.linalg.norm(after - points, axis=1)
side_c = np.linalg.norm(after - before, axis=1)
area = 0.5 * np.linalg.norm(np.cross(points - before, after - before), axis=1)
radius = np.full(len(points), np.inf)
curved = area > 1e-9
radius[curved] = (side_a[curved] * side_b[curved] * side_c[curved]) / (4.0 * area[curved])
```

Three sides of the triangle formed by each point and its two neighbours, the triangle's area
from a cross product, then Menger's formula for the circumradius. The guard is the point: a
straight section has near-zero area, so its radius stays `inf` (a straight is a circle of
infinite radius) and the division never blows up. `before`/`after` use `np.roll` on a closed
loop so neighbours wrap at the seam.

`build_ribbon_vertices` (`geometry.py:85`) is where the clamp does its job:

```python
lateral_unit = _unit(lateral)
effective_half_width = np.minimum(half_width_m, clamp_fraction * local_radius)
offset = effective_half_width[:, None] * lateral_unit
return np.stack([centreline + offset, centreline - offset], axis=1)
```

Push the centreline out by the half-width along the sideways vector to make the left edge,
and in for the right. The middle line is everything: the effective half-width is the *minimum*
of the nominal 6 m and 0.9 × the local radius. Where a corner is tighter than the ribbon is
wide, the ribbon shrinks to 90% of the radius so the inner edge stays on its own side of the
centre and never reaches the centreline (E-17). On a straight, `local_radius` is `inf`, the
minimum is just 6 m, and the ribbon is full width. `test_halfwidth_clamped_to_local_radius`
checks the inner edge stays strictly inside a 3 m arc.

`ribbon_self_intersects` (`geometry.py:104`) and `_edge_self_intersects` (`geometry.py:109`)
are the proof. The comment explains the shape of it: a real circuit is ~2000 stations, and a
naive every-pair-against-every-pair loop takes minutes, so this keeps the Python loop O(n)
and vectorises the inner comparison — segment i is tested against all later non-adjacent
segments at once (`geometry.py:116-124`):

```python
straddle_ab = _orient(a, b, others_start) * _orient(a, b, others_end) < 0
straddle_cd = (
    _orient_rows(others_start, others_end, a) * _orient_rows(others_start, others_end, b) < 0
)
if np.any(straddle_ab & straddle_cd):
    return True
```

`_orient` (`geometry.py:129`) is the signed area of the triangle formed by two points and a
third — positive for a left turn, negative for a right. `straddle_ab` is true where segment
i's two endpoints put the other segment's start and end on *opposite* sides (their orientation
signs multiply to negative). `straddle_cd` is the same test the other way round. A real
crossing needs both, hence the `&`. Adjacent segments share an endpoint, which gives a zero
orientation and never counts as a crossing — that is exactly what makes the closed-loop seam
legal instead of a false positive. This is asserted across every built circuit in the slow
test `test_no_self_intersection_across_ingested_circuits`.

`lap_length_m` and `within_tolerance` (`geometry.py:141`, `:149`) close it out: measure the
centreline's arc length, add the closing segment if the loop is not already sealed, and check
it against the reference within 5% (5.10.1 item 7, the one sourced tolerance in the config).

### elevation.py — decoration, never data (F-12)

The whole module is one function, and that is the point. `elevation_profile`
(`elevation.py:12`) always stamps `{"elevation": "stylised", "banking": "stylised"}` into the
flags. If a Z channel exists, it returns the smoothed Z multiplied by 1.5 and flags the source
`smoothed_z_exaggerated`; if Z is absent, it returns a flat profile (`np.zeros`) and flags
`flat_plus_camber`. Either way the metadata says "stylised" out loud, so the UI can never
present the height as measured (F-12). The build decides which branch runs by checking
whether the Z spread clears `flat_z_epsilon_m` (`build.py:69`) — below 1 m of range, Z reads
as absent noise and the flat fallback wins.

### annotations.py — corners, braking, X-mode

Three functions writing markers the frontend drapes along the ribbon by arc-length metre.
`corners_from_circuit_info` (`annotations.py:75`) just maps FastF1's official corner table to
plain dicts — these are *sourced*, the real corner numbers and angles. `braking_zones`
(`annotations.py:13`) is inferred: for each point it looks ahead within a 100 m window and, if
speed drops more than 50 km/h to the trough, marks the run as braking (5.10.1 item 6, both
numbers sourced from the spec). It then merges adjacent braking points into zones with an
entry and minimum speed. `xmode_sections` (`annotations.py:49`) finds every run where throttle
is at or above 99%, and returns them longest-first — the longest full-throttle stretches are
the stylised guess at where X-mode (low-drag) deployment belongs, until official section data
exists. Braking and X-mode are stylised; corners are sourced. The distinction rides through
to the metadata flags.

### export.py — writing the GLB

`ribbon_mesh` (`export.py:16`) turns the ribbon edges into a mesh. The `(N, 2, 3)` vertex
array reshapes straight to a flat `(2N, 3)` position list, left and right interleaved per
station. Then it stitches triangles (`export.py:28-33`):

```python
here, ahead = quad, (quad + 1) % station_count
left, right = 2 * here, 2 * here + 1
next_left, next_right = 2 * ahead, 2 * ahead + 1
triangles[2 * quad] = (left, right, next_left)
triangles[2 * quad + 1] = (right, next_right, next_left)
```

Between each station and the next there is a quad — four corners: this station's left and
right, the next station's left and right. Two triangles fill a quad, so each quad emits two
index triples. The `% station_count` on `ahead` is the whole closing trick: on the last quad
of a closed loop, `ahead` wraps to station 0, so the ring seals to the start with no
duplicated seam vertex. A closed loop gets `station_count` quads, an open strip one fewer.

`write_glb` (`export.py:37`) is pygltflib boilerplate: pack the positions and indices into one
byte blob, declare two accessors (one VEC3 float buffer for positions, one scalar uint buffer
for indices) and the buffer views that slice the blob, and save. The accessor min/max on the
positions is required by the glTF spec so a viewer can compute the bounding box. `write_metadata`
writes the sidecar JSON.

### build.py — the orchestrator

`run_build` (`build.py:134`) is the battery. It loads every ingested session from Postgres
(`_ingested_sessions`, `build.py:118`), groups them by event, and for each event picks the most
recent dry session, loads its fastest accurate lap, and runs `build_ribbon`. `build_ribbon`
(`build.py:43`) is the seven steps in sequence: resample, smooth the plan, branch on elevation,
frame, compute radius, extrude with the clamp, then annotate. Two details worth noting. The
comment at `build.py:56-58` explains why the loop is kept *periodic* rather than sealed with a
duplicate point — a duplicated start-finish point would be a zero-length segment that breaks the
tangent and the resample, so instead the loop stays open through geometry and only the *mesh*
closes the ring at export. And `_fit_window` (`build.py:198`) keeps the Savitzky-Golay window odd
and no longer than the series, so a short circuit shrinks the window instead of crashing.

The library is generated, not hand-listed (`circuit_index`, `build.py:38`). It writes an
`index.json` built purely from the circuits that had ingested data (F-08), so Madrid — which
has no 2026 session yet — simply does not appear until its first session lands (E-13). No
calendar is hard-coded anywhere; the data decides the library.

## How it connects

```
   FastF1 cache (GPS pos + car data)        Postgres (F01 ingested sessions)
            │                                        │
            │  load_fastest_lap_geometry             │  _ingested_sessions
            │  (pick_accurate.pick_fastest,          │  pick_most_recent_dry
            │   clean_pos_data — F01 reuse)          │
            └───────────────┬────────────────────────┘
                            ▼
        build.py:  resample ─► smooth ─► elevation ─► RMF frames
                        ─► curve_radius ─► clamp+extrude ─► annotate
                            │
                            ▼
        export.py:  data/circuits/<slug>/ribbon.glb + meta.json
                            │
                            ▼
                    data/circuits/index.json  ──►  F11 dashboard (R3F)
```

F04 is the 3D-foundation box of the spec 5.1 pipeline: telemetry and the ingested session
list in, one GLB plus metadata per circuit and a generated index out, consumed by the
frontend in F11. It reads nothing from F03 and writes nothing the simulation depends on —
the energy facts (H_max) stay in `circuits.yaml`, and elevation here is purely visual.

## Try it yourself

`make circuits` needs Postgres up and the FastF1 cache populated (it reads ingested sessions
and re-reads their telemetry). The fast geometry tests need neither:
`.venv/bin/python -m pytest tests/circuits -q`.

1. Change a stylised constant and predict the effect. In `configs/ribbon.yaml` raise
   `ribbon.width_m` from 12.0 to 24.0. Before running anything, predict what happens on a
   sub-6 m hairpin: does the ribbon get wider there? Then reason through the clamp in
   `build_ribbon_vertices`. You'll know it worked when you can say why the straights widen
   but Monaco's tight corners barely move — the `np.minimum` against `0.9 × radius` caps them.

2. Break the self-intersection guard and read the failure. In `build_ribbon_vertices`, delete
   the clamp so `effective_half_width = half_width_m` (a plain scalar), and run
   `.venv/bin/python -m pytest tests/circuits/test_geometry.py::test_ribbon_no_self_intersection_synthetic_hairpin -q`.
   You'll know it worked when it fails — the 12 m ribbon folds through the 5 m arc and
   `ribbon_self_intersects` returns True. Revert.

3. Break the frame periodicity. In `rotation_minimising_frames`, skip the `if closed:` block
   (return the transported normals without spreading the holonomy) and run
   `test_rmf_is_periodic_on_a_closed_loop`. You'll know it worked when the wrap-dot assertion
   fails: the seam carries the whole accumulated twist. Revert.

4. Prove Frenet is the wrong tool. Read `test_rmf_no_twist_flip_across_hairpin` and explain,
   in one sentence each, why `frenet_dots.min() < 0.0` is asserted and why `rmf_dots > 0.0` is
   asserted. You'll know it worked when you can say which line proves the problem and which
   proves the fix.

5. Add one small thing. In `annotations.xmode_sections`, add a `"rank"` field to each returned
   section (0 for the longest, 1 for the next, and so on) after the sort. Write a quick test in
   `tests/circuits/test_annotations.py` that asserts the longest section has rank 0. You'll know
   it worked when your test passes and the existing annotation tests still do.

## Check yourself

1. Why does the pipeline resample the centreline to uniform arc-length spacing before doing
   anything else? What downstream step would misbehave on raw time-sampled GPS?

2. Defend this design choice: the ribbon uses rotation-minimising frames rather than Frenet
   frames. What specifically goes wrong with Frenet, and where on a real circuit?

3. What is the holonomy angle on a closed loop, and what would the ribbon look like at the
   start-finish line if we did not correct for it?

4. Elevation is exaggerated 1.5× and flagged "stylised", but the corner numbers from CircuitInfo
   are not flagged stylised. What is the rule that decides, and why does F-12 care?

5. The circuit library is generated from ingested data rather than a hard-coded calendar. Give
   the concrete consequence for Madrid, and name the spec IDs behind the decision.

---

### Answers

1. Every step after resampling — smoothing, curvature via Menger, the half-width clamp —
   assumes points are evenly spaced along the track, and uses a fixed window count as a proxy
   for a fixed distance. Raw GPS bunches points where the car was slow (corners) and spreads
   them on straights, so a fixed-count smoothing window would cover a few metres in a corner
   and a hundred on a straight. Uniform 2 m spacing makes "11 samples" mean "22 metres"
   everywhere.

2. A Frenet frame builds its normal from the curve's own second derivative, and at an
   inflection point or hairpin — where the curve straightens and then bends the other way —
   that second derivative passes through zero and flips 180 degrees. The ribbon edge extruded
   along a flipping normal turns inside-out. It happens at every esse and every tight corner
   entry; on a real circuit, at somewhere like Silverstone's Maggotts-Becketts. RMF carries the
   normal forward with minimal rotation and never flips, which is the E-17 requirement.

3. Parallel transport around a closed curve does not generally return the starting vector to
   itself; the leftover rotation is the holonomy angle. Left uncorrected, the last station's
   frame and the first station's frame disagree by that angle, so the closing quad at
   start-finish would carry the entire twist in one jump and show a visible seam or a pinch. We
   measure the angle and spread it back evenly so the frame is periodic.

4. The rule is F-12: a number that only affects how the track *looks* is stylised; a number
   that is a real measurement is not. Elevation exaggeration and camber are visual inventions,
   so they are flagged; the CircuitInfo corners are FastF1's actual corner data, so they are
   sourced. F-12 cares because the dashboard must be able to tell a viewer which parts of the
   3D scene are measured and which are decoration — otherwise decoration masquerades as data.

5. `circuit_index` builds the library only from events that have an ingested session, so Madrid
   — with no session ingested yet — is absent from `index.json` and gets no GLB, and it appears
   automatically the moment its first session lands. No calendar is hard-coded. The spec IDs are
   F-08 (library generated from data, never hand-listed) and E-13 (Madrid absent until ingested).

## Ledger update

These rows were appended to `docs/learn/00-curriculum.md`:

| Concept | First taught in | One-line definition |
|---|---|---|
| GLTF / GLB mesh (positions + indices) | F04 | A 3D model as two lists — a flat vertex-position buffer and integer triangle indices into it; GLB packs the glTF JSON and buffer into one binary file the frontend loads (5.10.1). |
| Arc-length resampling | F04 | Re-dropping points at uniform distance along a path (every 2 m) instead of uniform time, so corners and straights get equal point density for smoothing and curvature. |
| Savitzky-Golay filter | F04 | Sliding-window smoothing that fits a low-order polynomial per window and takes its centre value, keeping corner shape while killing GPS noise; Z smoothed harder than X/Y. |
| Frenet vs rotation-minimising frames | F04 | Frenet's normal flips 180° at inflections/hairpins; RMF carries a sideways vector along the curve by parallel transport (double reflection) with minimal rotation, so the ribbon never twists (E-17). |
| Parallel transport and holonomy | F04 | Transport carries a frame forward with least turn; on a closed loop the residual twist (holonomy angle) is measured and spread over all stations so the frame is periodic and the seam is clean. |
| Menger curvature / radius of curvature | F04 | Local radius from three consecutive points, r = (a·b·c)/(4·area); inf on straights, small in hairpins — the ribbon half-width is clamped below it so tight corners cannot fold (5.10.1 item 4). |
| Segment-intersection orientation test | F04 | Two segments cross only if each straddles the other, tested by the sign of the triangle-orientation cross product; shared endpoints give zero and never count, so the loop seam is legal (E-17). |
| Stylised vs sourced provenance (visual data, F-12) | F04 | The anti-black-box rule for pixels: numbers that only change how the track looks (elevation, camber, width) are flagged `stylised` in config and metadata, so the UI never shows decoration as data. |
