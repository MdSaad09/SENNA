# F11 — Frontend shell + Circuit Explorer + Race Replay · approved plan

## Context

F00 left `frontend/` as a splash screen with the full pinned stack (react 18.3.1, R3F 8.18, drei 9.122, three 0.169 exact, zustand, react-query, tailwind, vitest) installed but unused. F04 committed three circuit ribbons (bahrain, hungarian, monaco: `ribbon.glb` + `meta.json`); F10 serves them plus simulation frames over REST. F11 builds the dashboard skeleton — views are routes, one canvas at a time — and the first two views: the annotated 3D circuit and a 22-car instanced replay that holds the frame budget. Views 3–6 get placeholder routes for F12/F13.

## Objective & spec anchors

- **F-28** — one canvas mounted at a time; views are routes, navigation unmounts; ≤ 4 Drei Html labels (selected car + podium), everyone else instanced sprite text. Shapes the whole architecture: no shell-level canvas, each view owns its `CanvasHost`.
- **F-29 / R-07** — generic liveries only (team colour + invented three-letter codes, no real team/driver/sponsor marks); the unofficial-project footer stays on every view.
- **E-18** — `webglcontextlost`/`webglcontextrestored` reload overlay on the canvas host.
- **5.10.2 rows 1–2** — View 1 annotations (corners, braking zones, X-mode, harvest + H_max) with stylised/inferred caveats in the legend; View 2 spline-interpolated mid-lap positions labelled illustrative.
- **5.10.3** — perf budget asserted where measurable: ≤ 150 draw calls in replay, ≤ 4 Html labels, LOD beyond 500 m, 60 fps target / 45 floor.
- **5.1 invariant 2** — every displayed number comes from the API; the dev overlay traces each figure to its response (run_id / model_version / env_config_hash / X-Model-Version header).

## Flagged spec divergences & gaps found while planning

1. **CircuitDetail hides the stylised flags.** `meta.json` carries `flags{elevation, banking, source, camber_deg?}` but the F10 API drops them, and 5.9.2 promises "energy zone metadata" that doesn't exist. F11 adds a `flags` passthrough field to `CircuitDetail` (api/schemas.py + api/routes/circuits.py + test) so the View 1 legend derives its caveats from data instead of hardcoding. Recorded as closing an F10 gap toward 5.9.2.
2. **No harvest-zone data exists anywhere** (F04 never emitted it; 5.10.2 row 1 wants "harvest zones + per-circuit H_max"). Harvest is rendered as a restyled inner strip over the braking zones — physically where the MGU-K harvests — labelled "harvest shown at braking zones — stylised" in the legend. H_max comes from the API's `h_max_mj`.
3. **No pit-lane spline** (5.10.1 item 6 assigned it to F04; it was never emitted). View 1 renders no pit lane; View 2 shows in-pit cars with a lateral offset + reduced scale, labelled stylised. Recorded as a known F04 gap, not fixed here.
4. **No router is installed and 5.9.1 pins none.** Add `react-router-dom ^6.30` (v6, not v7: stable React-18 line, no Remix surface, zero React-19 pressure; URL params give `/replay?run=` and feed F13's deep links). After install, verify `npm ls react` still resolves a single react 18.3.1 — no duplicate React in the tree.
5. **The circuit "library" is 25 entries in configs/circuits.yaml but only 3 built ribbons.** "Both views render every circuit in the library" is read as: every circuit with `coverage.ribbon = true` renders fully; the rest get an honest "ribbon not built" state driven by the F-08 coverage flags.
6. **Frontend constants cannot live in configs/*.yaml** (the browser never sees repo yaml). They live in one module, `frontend/src/config/constants.ts`, under the same provenance-comment discipline; values that mirror a yaml (page size, playback speeds) say so in the comment.
7. **`CarState.s_track` is a lap fraction, not metres** — a display-only synthesis from gap-to-leader (frames.py docstring). The replay multiplies by `lap_length_m`, interpolates between per-lap snapshots, and the UI carries the "mid-lap positions illustrative" caption. Era-2024 runs have 20 cars — grid size is always `frames[0].cars.length`, never a hardcoded 22.

## Deliverables

**One backend touch**
- `api/schemas.py`, `api/routes/circuits.py`, `tests/api/test_circuits.py` — `flags: dict | None` passthrough on CircuitDetail (divergence 1).

**Shell & plumbing (`frontend/src/`)**
- `main.tsx` (mod) — QueryClientProvider + RouterProvider.
- `routes.tsx` — route table: `/` → `/circuit`; `/circuit`, `/replay`, `/energy`, `/tyres`, `/live`, `/counterfactual` (last four render `StubView`); lazy view imports. The F-28 guarantee lives here.
- `App.tsx` (mod) — becomes the Shell: nav header, `<Outlet/>`, the existing R-07 footer verbatim, DevOverlay mount.
- `config/constants.ts` — every frontend number, provenance-commented (table below).
- `config/liveries.ts` — 11 generic team colours, `carLivery(id)` → colour + code `C01..C22`, ego accent (F-29).
- `api/types.ts`, `api/client.ts`, `api/provenance.ts`, `api/queries.ts` — TS mirrors of the 5.9.2 schemas; fetch wrapper on `VITE_API_BASE` (default `/api`, F-27) that records every response into a provenance ring buffer (traceId, method, path, status, X-Model-Version, run_id/model_version/env_config_hash when present); react-query hooks incl. status polling and the sequential `/frames` page loop.
- `stores/uiStore.ts` (bloom, dev overlay, context-lost), `stores/replayStore.ts` (playback state; pure `advancePlayhead` exported; transient subscriptions so nothing re-renders at 60 fps).

**Canvas infrastructure (`components/`)**
- `CanvasHost.tsx` — the single `<Canvas>` per view; Z-up via one `group rotation=[-π/2,0,0]`; wires context-loss; mounts PerfProbe.
- `ContextLossOverlay.tsx` — E-18 hook + reload overlay, StrictMode-safe.
- `PerfProbe.tsx` + `perfBus.ts` — rolling fps + `gl.info.render.calls` at 2 Hz, dev warning past the 150 budget, `window.__SENNA_PERF` for the trace.
- `DevOverlay.tsx` — backtick-toggled: provenance table, perf vs budget, simulate-context-loss button (the interpretability-contract row).
- `QualityToggle.tsx` + `Bloom.tsx` — bloom via three's own jsm EffectComposer/UnrealBloomPass (no new dep), default off below the GPU heuristic, disposed on toggle-off.

**Pure geometry/data libs (`lib/`)** — all testable in jsdom, no WebGL at module scope
- `centreline.ts` — rebuild centreline from the GLB's interleaved left/right vertex pairs (midpoint of 2i/2i+1); cumulative arc-length table; `sampleAt(m)`/`tangentAt(m)` with closed-ring wrap.
- `ribbonStrips.ts` — merged strip geometries for braking/X-mode/harvest zones along `[start_m, end_m]`, wrap-splitting, lifted `ANNOTATION_LIFT_M`.
- `progress.ts` — unwrap per-lap `s_track` (mod-1) into monotone progress; Fritsch–Carlson monotone cubic interpolant (Catmull-Rom can overshoot → cars would reverse).
- `labels.ts` — pure `labelledCars(cars, selectedId)` → ≤ 4 (podium ∪ selected).
- `labelAtlas.ts` — canvas-2D texture atlas of car codes + per-instance UV offsets → all sprite text in **one** draw call (the 5.10.3 "instanced sprite text").
- `gpuHeuristic.ts` — conservative bloom default from the unmasked renderer string.

**View 1 (`views/circuit/`)** — `CircuitExplorerView` (picker with coverage badges, empty state for `gltf_url: null`), `CircuitRibbon` (positions extracted from the GLB — `gltf.scene` never mounted, so drei's cache never fights disposal; own geometry + normals + strips + start line), `CornerMarkers` (one InstancedMesh of posts placed by `distance_m` — the meta's corner x,y are decimetres and unusable — plus drei Text numbers), `Legend` (caveats driven by `detail.flags`). Static scene, no per-frame work beyond OrbitControls. ~27 draw calls.

**View 2 (`views/replay/`)** — `RaceReplayView` (`?run=` param; RunPicker: SimulationCreate form → POST → poll → replay; agent HUD strip showing soc/harvest/deploy from frames), `ReplayScene` (owns the one playback `useFrame`: clock = `delta · speed / nominal_lap_s`; per car interpolated progress → `sampleAt(frac(p) · lap_length_m)` + tangent heading → instance matrix; `frustumCulled = false`; colours set once via `setColorAt` before first render), `CarInstances` (body + detail InstancedMeshes; LOD: detail mesh and sprite labels drop beyond 500 m), `CarLabels` (≤ 4 Html slots on stable-keyed groups + the atlas sprite mesh, camera-billboarded in the same loop), `TransportControls` (play/pause, speeds 1/5/10/30, scrub slider writing through a transient subscription; "mid-lap positions illustrative" caption). ~9 draw calls; ~25 with bloom — order-of-magnitude headroom under 150.

**Test fixtures (`test/`)** — `mockR3F.tsx` (Canvas → plain `<canvas>`, drei Html → div, useGLTF → fixture), `ribbonFixture.ts` (4-station square ribbon with known arc lengths), `apiFixtures.ts` (20- and 22-car frame fixtures, fetch stub), `prng.ts` (mulberry32 for seeded property loops).

## Constants & configs

All in `frontend/src/config/constants.ts` unless noted; each line carries its provenance comment (divergence 6).

| Name | Value | Origin |
|---|---|---|
| MAX_DRAW_CALLS_REPLAY | 150 | sourced — 5.10.3 |
| MAX_HTML_LABELS | 4 | sourced — 5.10.3 |
| FPS_TARGET / FPS_FLOOR | 60 / 45 | sourced — 5.10.3 |
| LOD_DISTANCE_M | 500 | sourced — 5.10.3 |
| PLAYBACK_SPEEDS | [1, 5, 10, 30] | sourced — 5.9.3; mirrors configs/serving.yaml `playback.speeds` |
| FRAMES_PAGE_SIZE | 100 | operational — mirrors configs/serving.yaml `frames.page_size`; stepping only, stop condition is race_laps |
| EGO_CAR_ID | 0 | sourced — F10 CarState contract (api/schemas.py) |
| RUN_STATUS_POLL_MS | 1000 | operational — REST polling half as eager as the server's own 0.5 s WS poll |
| ANNOTATION_LIFT_M | 0.2 | stylised — z-fighting offset for zone strips |
| PROVENANCE_LOG_CAP | 50 | operational — ring buffer bound |
| LIVERY_PALETTE (11 colours) + CAR_CODES C01–C22 | in `config/liveries.ts` | stylised — F-29 generic liveries |
| Car body dimensions | ~5.6 × 2.0 m box | stylised — 2026 car footprint, visual only |
| GPU heuristic pattern list | renderer-string table | operational — bloom default; conservative off |

No Python-side constant changes; the `flags` passthrough introduces no numbers.

## Tests first

Written red before implementation, in this order (vitest + jsdom; R3F mocked at the Canvas boundary — jsdom cannot create WebGL):

1. `liveries.f29.test.ts` — **F-29 asset check**: fs-walk of `src/**` + `index.html` (tests excluded) against a trademark deny-list (teams, sponsors, driver surnames; word-boundary rules for short marks); livery table shape: 11 unique hex colours, codes match `/^C(0[1-9]|1\d|2[0-2])$/`, ≤ 11 teams via `floor(id/2)`.
2. `centreline.test.ts` — midpoints recovered from interleaved pairs; cumulative s `[0,10,20,30]`, closed total 40 on the square fixture; `sampleAt` interior/wrap/negative; tangent direction.
3. `ribbonStrips.test.ts` — zone→station ranges, wrap-around zone splits in two, lift applied.
4. `progress.test.ts` — **property (seeded loop, 500 cases)**: unwrapped progress strictly increasing, `frac` matches input, per-step advance sane; interpolant non-decreasing on dense evaluation and exact at knots. Seeded-loop with printed seed instead of a fast-check dep — four invariants don't earn a new library.
5. `labels.test.ts` — **property (seeded loop)**: grids 1–22, any selection → `labelledCars` ≤ 4 always; 3 when the selected car is on the podium; podium always included.
6. `routeMount.test.tsx` — **the F-28 test**: real route table in `createMemoryRouter`, Canvas mocked to a bare `<canvas>`; navigate `/circuit → /replay → /energy → /circuit`; exactly 1 canvas on canvas routes, 0 on stubs, never 2 anywhere.
7. `ContextLossOverlay.test.tsx` — synthetic `webglcontextlost` (asserting `defaultPrevented`) shows the overlay, `webglcontextrestored` clears it; StrictMode double-mount yields exactly one overlay; unmount detaches.
8. `client.test.ts` / `provenance.test.ts` — URL building, X-Model-Version capture, run_id/env_config_hash extraction, ring-buffer cap + notify.
9. `replayStore.test.ts` — `advancePlayhead`: speed scaling, clamp + pause at final lap, scrub bounds.
10. `CarLabels.test.tsx` — component level: 22-car fixture renders 4 mocked Html labels with midfield selection, 3 with podium selection.
11. `CircuitExplorerView.test.tsx` / `RaceReplayView.test.tsx` — legend caveats render from a flags fixture; picker shows coverage states; era-2024 fixture drives 20 cars (nothing hardcodes 22).
12. `gpuHeuristic.test.ts`, `labelAtlas.test.ts` — table-driven heuristic; atlas layout math (drawing itself is runtime-only; jsdom has no 2D context).
13. Python: extend `tests/api/test_circuits.py` for the `flags` passthrough.

**Not testable in jsdom — documented runtime checklist in the ship report:** real draw calls vs 150 via the dev overlay, the Chrome performance trace of a full 70-lap replay (45 fps floor), all three GLBs parsing, bloom/LOD visuals, real context loss via the overlay's `WEBGL_lose_context` button.

## Edge cases handled

- **E-18** — context-loss overlay on the one canvas host; one canvas per route keeps GPU pressure minimal by construction.
- **E-16 (adjacent)** — View 2 replays *stored* frames over REST (the E-16 source of truth); the WS playback client is F13's.
- **F10 divergence 4** — 20-car era-2024 grids: car count always derived from the frame.
- **Retired cars** — `s_track` freezes server-side; the frozen fraction parks the car on the ribbon instead of orbiting it.
- **Lapped cars** — mod-1 wrap unwrapped to monotone progress; a car more than a lap down folds onto its visual position (display-only, labelled illustrative).
- **Zones crossing s = 0** — strip builder splits wrap-around zones.
- **`gltf_url: null` / missing coverage** — explicit "ribbon not built" state, never a crash (F-08 flags shown in the picker).
- **InstancedMesh culling** — `frustumCulled = false` (the classic disappearing-cars bug); colours set before first render (three 0.169 `setColorAt` gotcha).
- **StrictMode double effects** — all listeners/intervals/subscriptions cleanup-symmetric; pinned by test 7.

## Acceptance checklist (Done means)

- [ ] Both views render every circuit in the library — full render where `coverage.ribbon` is true, honest coverage state otherwise (divergence 5)
- [ ] Chrome trace of a full 70-lap replay holds the 45 fps floor (run on Saad's Mac; reference GPU is GTX 1660-class — hardware noted in the result, OQ-2 style)
- [ ] Replay stays ≤ 150 draw calls and ≤ 4 Html labels, asserted by PerfProbe + tests
- [ ] The R-07 footer is present on every route
- [ ] Every stylised element is labelled in the UI: elevation/banking caveats from `flags`, X-mode "inferred", harvest "shown at braking zones — stylised", mid-lap positions "illustrative", pit-offset "stylised"
- [ ] Dev overlay traces every displayed number to its API response (endpoint + ids + X-Model-Version)
- [ ] `npm ls react` resolves a single react 18.3.1 after the router install
- [ ] `npm test`, `tsc -b`, `npm run lint`, `pytest -m "not slow"` all green; CI green after push (incl. the F-27 bundle grep)

## Out of scope

- Views 3–6 beyond placeholder routes (F12, F13); WS client, speed-synced streaming, decision cards (F13); demo polish (F15).
- Real-race replay from `GET /races/{year}/{round}` — View 2 replays simulation runs only; the endpoint stays for later.
- Building ribbons for the other 22 circuits (needs ingestion; `make circuits` is not CI-runnable).
- Pit-lane spline emission (F04 gap, recorded), harvest-zone *data* (only the stylised presentation ships).
- Deep links with seed + circuit in the query string (F13 deliverable; `?run=` here is just view state).

## Decisions (Saad, 22 Jul 2026)

1. **Router approved** — `react-router-dom ^6.30` (v6 line), with the post-install check that `npm ls react` resolves a single react 18.3.1.
2. **`flags` passthrough approved** — divergence recorded above.
3. **Library reading approved** — coverage-driven honest states for unbuilt ribbons. **Follow-up (not F11):** before the presentation video, run `make circuits` across all ingested events and commit the GLBs (~100 KB each, ~2.6 MB total) so the demo and a clean clone show a full circuit library rather than 3 circuits.

## Ship-process notes

- Cold-cache ruff lint before the final gate — the warm cache has hidden I001 on tests-first features before (F03–F06 lesson).
- Verify the Actions page after /land.

