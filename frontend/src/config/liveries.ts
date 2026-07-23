// Generic liveries (F-29): eleven invented team colours, two cars per team, codes
// C01-C22. Nothing here may reference a real team, sponsor or driver — the
// liveries.f29 test walks every shipped file to hold that line.

// stylised — a hand-picked wheel of distinct hues that read apart against the
// neutral-950 track scene; no palette source, purely visual
export const TEAM_COLOURS = [
  "#e23d3d",
  "#3d7be2",
  "#3de28f",
  "#e2c43d",
  "#a03de2",
  "#e2733d",
  "#3dcfe2",
  "#e23da8",
  "#8fe23d",
  "#7a86a8",
  "#c4b08e",
];

// stylised — the ego car keeps its team colour but gets this accent ring in the UI
export const EGO_ACCENT = "#ffffff";

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
