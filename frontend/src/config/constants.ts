// Every number the frontend owns, with its provenance — the configs/*.yaml contract
// (root CLAUDE.md) carried into the one place the browser can actually read
// (docs/plans/F11-plan.md, divergence 6). Values mirrored from a yaml say so.

export const MAX_DRAW_CALLS_REPLAY = 150; // sourced — 5.10.3 replay draw-call budget
export const MAX_HTML_LABELS = 4; // sourced — 5.10.3: selected car + podium (F-28)
export const FPS_TARGET = 60; // sourced — 5.10.3, GTX 1660-class reference
export const FPS_FLOOR = 45; // sourced — 5.10.3, the trace must never dip below
export const LOD_DISTANCE_M = 500; // sourced — 5.10.3: detail and sprite text drop beyond

export const PLAYBACK_SPEEDS = [1, 5, 10, 30]; // sourced — 5.9.3; mirrors configs/serving.yaml playback.speeds

// operational — mirrors configs/serving.yaml frames.page_size; page stepping only,
// the loop stops on the first short page
export const FRAMES_PAGE_SIZE = 100;

export const EGO_CAR_ID = 0; // sourced — F10 CarState contract (api/schemas.py)

// operational — half as eager as the server's own 0.5 s run poll (serving.yaml ws.status_poll_s)
export const RUN_STATUS_POLL_MS = 1000;

export const ANNOTATION_LIFT_M = 0.2; // stylised — floats zone strips above the ribbon to dodge z-fighting

export const PROVENANCE_LOG_CAP = 50; // operational — plenty for a session, bounded for memory

export const DEV_OVERLAY_KEY = "`"; // operational — the backtick toggles the provenance overlay

export const PERF_SAMPLE_MS = 500; // operational — 2 Hz keeps the probe invisible to the frame budget

// stylised — camera framing for a 3-6 km ribbon; far plane clears the longest circuit
export const CAMERA = { fov: 50, near: 1, far: 20_000, position: [0, 900, 900] as const };

// stylised — the 2026 car footprint as a readable box, visual only
export const CAR_DIMENSIONS_M = { length: 5.6, width: 2.0, height: 1.0 };

// stylised — in-pit cars pull aside and shrink; there is no pit-lane spline in the
// F04 artifacts (plan divergence 3), and the legend says so
export const PIT_LATERAL_OFFSET_M = 9;
export const PIT_SCALE = 0.7;

export const LABEL_HEIGHT_M = 6; // stylised — labels hover clear of the car roofline
export const SPRITE_LABEL_SIZE_M = 7; // stylised — sprite text quad edge at replay zoom

// stylised — a restrained glow: highlights only, never bloom-the-whole-track
export const BLOOM_STRENGTH = 0.35;
export const BLOOM_RADIUS = 0.6;
export const BLOOM_THRESHOLD = 0.85;
