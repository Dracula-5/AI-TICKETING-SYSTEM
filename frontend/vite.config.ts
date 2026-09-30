/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the backend so the SPA and API share an
// origin — the httpOnly refresh cookie then works exactly as it does behind
// the production reverse proxy.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false, ws: true },
    },
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        // Long-lived vendor chunks so app deploys don't bust the library cache.
        // Charts are deliberately NOT a manual chunk: they stay inside the
        // lazily loaded dashboard chunk, so requesters never download them.
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/](@mui|@emotion)[\\/]/.test(id)) return "mui";
          if (/[\\/](react|react-dom|react-router|scheduler)[\\/]/.test(id)) return "react";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
    // Full-app render tests take seconds on a loaded CI runner; 5 s default flakes.
    testTimeout: 20_000,
    coverage: { provider: "v8", include: ["src/**/*.{ts,tsx}"], exclude: ["src/test/**", "src/main.tsx"] },
  },
});
