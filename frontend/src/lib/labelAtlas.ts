// One texture, one draw call: every car code is pre-drawn into a square grid and
// the sprite mesh picks its cell with a per-instance UV offset (5.10.3 "instanced
// sprite text"). Layout math is pure so jsdom can pin it; drawing needs a real 2D
// context and stays lazy.

export interface AtlasLayout {
  cols: number;
  rows: number;
  cellU: number;
  cellV: number;
  uvOffset(index: number): [number, number];
}

export function atlasLayout(codes: string[]): AtlasLayout {
  const cols = Math.max(1, Math.ceil(Math.sqrt(codes.length)));
  const rows = Math.max(1, Math.ceil(codes.length / cols));
  const cellU = 1 / cols;
  const cellV = 1 / rows;
  return {
    cols,
    rows,
    cellU,
    cellV,
    uvOffset: (index) => [(index % cols) * cellU, Math.floor(index / cols) * cellV],
  };
}

// operational — 128 px cells keep three glyphs crisp at replay zoom without
// pushing the atlas past 1024^2 for a 22-car grid
const CELL_PX = 128;

export function buildAtlasCanvas(codes: string[], colours: string[]): HTMLCanvasElement {
  const layout = atlasLayout(codes);
  const canvas = document.createElement("canvas");
  canvas.width = layout.cols * CELL_PX;
  canvas.height = layout.rows * CELL_PX;

  const context = canvas.getContext("2d");
  if (context === null) {
    throw new Error("label atlas needs a 2D canvas context — headless DOMs cannot draw it");
  }

  context.textAlign = "center";
  context.textBaseline = "middle";
  // stylised — 0.42 of the cell keeps three bold glyphs inside it with margin
  context.font = `bold ${Math.round(CELL_PX * 0.42)}px ui-monospace, monospace`;
  codes.forEach((code, index) => {
    const [u, v] = layout.uvOffset(index);
    const x = u * canvas.width + CELL_PX / 2;
    const y = v * canvas.height + CELL_PX / 2;
    context.fillStyle = colours[index] ?? "#ffffff";
    context.fillText(code, x, y);
  });
  return canvas;
}
