// The one palette. Before F23 the dashboard had two colour surfaces that knew nothing
// about each other: Tailwind's neutral ramp in className strings, and a scatter of inline
// hexes in the recharts and R3F code — including SocBar importing SOC_TINT out of
// SocPanel to keep two blues in step. Everything now starts here, and tailwind.config.js
// mirrors PALETTE under its `senna` namespace (palette.tailwind.test.ts is the joint).

// stylised — the ramp is sampled from Saad's reference screenshots
// (docs/reference_images/, 11 Aug 2026) rather than invented: the PNGs were decoded and
// their dominant colours counted, so these are the actual values in the design he
// approved. Percentages below are each colour's share of the shot it dominates.
export const PALETTE = {
  ground: "#0b1014", // 41.3% of shot 3 — page ground, header bar, tooltip fill
  surface: "#121a1f", // 85.1% of shot 1 — panel body, the workhorse
  raised: "#1a242b", // 62.0% of shot 2 — canvas field, panel headers, hover
  line: "#26333c", // the hairline border in all three shots
  text: "#e6edf1", // figures and headings
  muted: "#c9d0d7", // body copy
  faint: "#637481", // micro-labels, axis ticks
  ghost: "#515c63", // disclaimers and disabled state
  accent: "#6bd6c3", // the mint: wordmark, live state, the panel-header tick
  danger: "#b13f4d", // failures, and the soft compound shares it
} as const;

// stylised — the conventional soft-to-hard ranking reads red / amber / white, and the
// soft and medium hues are sampled from the reference's stint bar. The hues are chosen,
// not lifted from any supplier's scheme, and no supplier is named anywhere in this
// codebase (F-29). Keys are the served compound strings, senna/env/scenario.py:21.
export const COMPOUND_COLOURS: Record<string, string> = {
  SOFT: "#b13f4d",
  MEDIUM: "#b29337",
  HARD: "#c9d0d7",
  INTERMEDIATE: "#3f9e58",
  WET: "#3b74c4",
};

// stylised — recharts furniture, previously repeated hex-by-hex in SocPanel,
// EnergyBarsPanel and DeltaChartPanel. Retuned from the old neutral greys onto the ramp
// above so the charts sit in the same room as the panels around them.
export const CHART = {
  soc: "#4fb0d9", // state of charge: the one cool hue, distinct from the mint
  harvest: "#3f9e8f", // recovery, deliberately adjacent to the accent
  deploy: "#e08a3c", // spend, the warm opposite of harvest
  pitMark: "#637481",
  gridLine: "#1a242b",
  axis: "#637481",
  tooltipBg: "#0b1014",
  tooltipLine: "#26333c",
} as const;

// stylised — R3F scene tints. The grip surface keeps a green-amber-red reading because
// the cliff is the whole point of that view, but it now borrows the compound hues rather
// than running its own traffic-light palette.
export const SCENE = {
  braking: "#d08a2c",
  xmode: "#8b6fd4",
  harvestZone: "#3f9e8f",
  deck: "#1a242b",
  cornerMarker: "#c9d0d7",
  cornerLabel: "#e6edf1",
  gripHigh: "#3f9e58",
  gripLow: "#b13f4d",
  gripCliff: "#b29337",
} as const;
