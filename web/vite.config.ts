import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Local dev: drop a pipeline summary into public/data/summary.json and the dev server
// exposes it at /data/summary.json, matching the production path.
export default defineConfig({
  plugins: [react()],
  build: { assetsDir: "assets", sourcemap: false },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
  },
});
