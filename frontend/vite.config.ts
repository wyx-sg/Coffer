/// <reference types="vitest" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite + Tauri 2 conventions:
//   - clearScreen: false        keep Tauri's terminal output visible
//   - server.strictPort: true   Tauri expects a known port
//   - envPrefix: ["VITE_", "TAURI_ENV_*"]  let Tauri inject build-time env
//
// `TAURI_DEV_HOST` is set by `tauri dev` when running on a remote host
// (mobile dev). Falls back to localhost for browser-only dev.
const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  envPrefix: ["VITE_", "TAURI_ENV_*"],
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 5174,
        }
      : undefined,
    watch: {
      // Ignore the Tauri Rust source tree so vite HMR doesn't thrash on
      // cargo writes to target/.
      ignored: ["**/src-tauri/**"],
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
