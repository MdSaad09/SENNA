import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Browser code only ever sees VITE_API_BASE=/api; the proxy target is a
// server-side detail, so a compose service name is allowed here (5.11.2, F-27).
const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      "/api": { target: apiProxyTarget, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/vitest.setup.ts",
  },
});
