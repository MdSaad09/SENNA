// Generic liveries (F-29): eleven invented team colours, two cars per team, codes
// C01-C22. Nothing here may reference a real team, sponsor or driver — the
// liveries.f29 test walks every shipped file to hold that line.

// stylised — eleven hues spaced around the wheel, held at the saturation and lightness
// the rest of the dashboard runs at (see config/palette.ts). The first cut of these was a
// fully saturated rainbow chosen against a neutral scene; on the F23 ground it read as a
// bag of sweets next to a muted teal instrument, which is the one thing the palette exists
// to prevent. They still have to separate 22 cars at sprite size, so hue does the work and
// saturation stays out of it.
export const TEAM_COLOURS = [
  "#d96b6b",
  "#6b9dd9",
  "#6bd699",
  "#d9c46b",
  "#a86bd9",
  "#d9946b",
  "#6bcdd9",
  "#d96bab",
  "#a8d96b",
  "#8f9bb3",
  "#c2b191",
];

// stylised — the ego car keeps its team colour but gets the dashboard accent wherever the
// UI has to point at it, so "ours" is the same mint in the timing tower, the delta chart
// and the scene. Written out rather than imported: palette.ts is the source, and the
// liveries walk (F-29) reads this file as text
export const EGO_ACCENT = "#6bd6c3";

export interface Livery {
  colour: string;
  code: string;
  team: number;
}

export function carLivery(id: number): Livery {
  const team = Math.floor(id / 2);
  return {
    colour: TEAM_COLOURS[team % TEAM_COLOURS.length],
    code: `C${String(id + 1).padStart(2, "0")}`,
    team,
  };
}
