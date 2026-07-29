// Runs only via `make demo-check` against a warmed local stack — never CI, never
// vitest (vite.config.ts excludes e2e/). No retries: the spec measures the 5.13
// first beat, and a retry would report a failed beat as a passed one.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  retries: 0,
  use: {
    // operational — the compose/vite dev server origin (docker-compose.yml)
    baseURL: process.env.DEMO_BASE_URL ?? "http://localhost:5173",
  },
});
