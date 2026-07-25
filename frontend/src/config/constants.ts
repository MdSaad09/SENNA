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

// operational — reconnect backoff: first retry no more eager than the server's own
// 0.5 s store poll (serving.yaml ws.status_poll_s), doubling to a cap that keeps the
// worst gap under what a demo viewer tolerates (the F13 spec stakes the demo on it)
export const WS_RECONNECT_BASE_MS = 500;
export const WS_RECONNECT_FACTOR = 2;
export const WS_RECONNECT_MAX_MS = 8000;

// sourced — HTTP 101 Switching Protocols: the status a WS open represents in the
// provenance log, which only speaks HTTP statuses
export const WS_STATUS_OPEN = 101;

// operational — the midfield default start (first demo run shows overtakes), hoisted
// so RunPicker and the /live deep link cannot drift apart
export const DEFAULT_GRID_POSITION = 8;

// sourced — mirrors senna/explain/cards.py _PIT_CALLS / _MODE_CALLS verbatim: the
// card's probability arrays arrive unlabelled and these strings are their names (A-03)
export const PIT_ACTION_LABELS = [
  "stay out",
  "pit for Soft",
  "pit for Medium",
  "pit for Hard",
  "pit for Intermediate",
  "pit for Wet",
];
export const MODE_ACTION_LABELS = ["conserve energy", "run balanced", "attack", "defend"];

// stylised — the divergence flash: long enough to register at 30x, rose because no
// team colour or series tint claims it (liveries.ts, SocPanel, CircuitRibbon)
export const DIVERGENCE_FLASH_MS = 900;
export const DIVERGENCE_FLASH_TINT = "#f43f5e";

// stylised — the app's neutral-950 backdrop; drei's scissored views never clear
// unless the pane scene sets an explicit background, so the CSS show-through trick
// the full-canvas views use cannot work there
export const PANE_BACKGROUND = "#0a0a0a";

// operational — half as eager as the server's own 0.5 s run poll (serving.yaml ws.status_poll_s)
export const RUN_STATUS_POLL_MS = 1000;

export const ANNOTATION_LIFT_M = 0.2; // stylised — floats zone strips above the ribbon to dodge z-fighting

export const PROVENANCE_LOG_CAP = 50; // operational — plenty for a session, bounded for memory

export const DEV_OVERLAY_KEY = "`"; // operational — the backtick toggles the provenance overlay

export const PERF_SAMPLE_MS = 500; // operational — 2 Hz keeps the probe invisible to the frame budget

// stylised — camera framing for a 3-6 km ribbon; far plane clears the longest circuit
export const CAMERA = { fov: 50, near: 1, far: 20_000, position: [0, 900, 900] as const };

// operational — device-pixel-ratio clamp: retina sharpness without paying 3x pixels
// on high-density laptop panels (the classic hidden fps cost)
export const DPR_RANGE: [number, number] = [1, 2];

// sourced — mirrors configs/ribbon.yaml elevation_exaggeration; the legend quotes it
// (the value is baked into the committed GLBs, so a yaml retune requires make circuits)
export const ELEVATION_EXAGGERATION = 1.5;

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

// The tyre surface's temperature axis. The fit is age-only (T5), so the temperature
// dimension is stylised and the on-view label says so — see docs/plans/F12-plan.md
// divergence 1. sourced — obs #32 normaliser (T - 15) / 45 spans a 15-60 C range.
export const TYRE_TEMP_AXIS_MIN_C = 15;
export const TYRE_TEMP_AXIS_MAX_C = 60;
// stylised — the readout slice, mirrors configs/env.yaml track_temp_dry_c; the surface
// equals the served fitted curve exactly here, and every hover number is read off it
export const TYRE_TEMP_REF_C = 30;
// stylised — how far the stylised temperature response may bend grip from the fitted
// slice, at the axis extremes; understated on purpose, the label owns the honesty
export const TYRE_TEMP_GRIP_PENALTY = 0.08;
// operational — surface tessellation; one grid mesh in a single draw call either way,
// so the density is only a smoothness-vs-vertex-count choice
export const GRIP_AGE_SAMPLES = 64;
export const GRIP_TEMP_SAMPLES = 33;
