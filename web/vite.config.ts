import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev: copy a locally built summary to public/data/summary.json (see README) and Vite
// serves it at /data/summary.json, the same path CloudFront serves in production.
export default defineConfig({
  plugins: [react()],
  build: { assetsDir: "assets", sourcemap: false },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
  },
});
