/** @type {import('tailwindcss').Config} */

// The `senna` colours mirror PALETTE in src/config/palette.ts. They are written twice
// on purpose: importing a .ts module into this config needs allowJs across the
// Tailwind/Vite/TS boundary, and a drift test (palette.tailwind.test.ts) is the cheaper
// joint. Change one, change both, or that test fails.

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        senna: {
          ground: "#0b1014",
          surface: "#121a1f",
          raised: "#1a242b",
          line: "#26333c",
          text: "#e6edf1",
          muted: "#c9d0d7",
          faint: "#8a99a6",
          ghost: "#7d8994",
          accent: "#6bd6c3",
          danger: "#d9556a",
        },
      },
      fontFamily: {
        // stylised — the reference sets everything in one mono face; figures line up in
        // tables and the micro-labels get their machined look
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      // stylised — the type scale, read off the reference. Three sizes and nothing
      // between them: a micro caption, a label, and the figure it labels
      fontSize: {
        micro: ["0.625rem", { lineHeight: "1rem", letterSpacing: "0.18em" }],
        label: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.08em" }],
        figure: ["0.9375rem", { lineHeight: "1.25rem" }],
      },
      borderRadius: {
        // stylised — the reference's panels are square to within a pixel; anything
        // rounder reads like a consumer app rather than an instrument
        panel: "2px",
      },
    },
  },
  plugins: [],
};
