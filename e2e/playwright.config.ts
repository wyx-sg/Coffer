import { defineConfig, devices } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ESM-compatible equivalents of __dirname / __filename
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ROOT = path.resolve(__dirname, "..");

export default defineConfig({
  fullyParallel: false, // sequential — all tests share the same daemon instance
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],

  webServer: [
    {
      // Daemon: isolated HOME via start_daemon.sh, always on port 18000.
      // reuseExistingServer=true in local dev so repeated `npm test` runs
      // reuse the already-running daemon rather than fighting TCP TIME_WAIT.
      // In CI (reuseExistingServer=false) a fresh daemon is always spawned.
      // timeout=90s to accommodate the 45s port-wait in start_daemon.sh plus
      // ~5s for Alembic migrations and uvicorn startup.
      command: "bash ./scripts/start_daemon.sh",
      url: "http://127.0.0.1:18000/api/v1/daemon/status",
      timeout: 90_000,
      reuseExistingServer: !process.env.CI,
      cwd: __dirname,
    },
    {
      // Vite dev server pointed at the e2e daemon.
      // IMPORTANT: reuseExistingServer is intentionally false (even in local
      // dev) for the Vite entry.  A reused `make dev` Vite instance lacks
      // VITE_COFFER_BASE_URL, so the app silently falls back to port 8000
      // (no daemon there) and all API calls fail with "Failed to fetch".
      // The daemon entry above still reuses to avoid TCP TIME_WAIT delays;
      // Vite starts quickly enough that a fresh start per run is fine.
      command: "npm run dev -- --port 5173",
      url: "http://localhost:5173",
      timeout: 60_000,
      reuseExistingServer: false,
      cwd: path.join(ROOT, "frontend"),
      env: {
        VITE_COFFER_BASE_URL: "http://127.0.0.1:18000/api/v1",
      },
    },
  ],

  projects: [
    // -----------------------------------------------------------------------
    // web — browser-driven acceptance tests for the Coffer frontend UI
    // -----------------------------------------------------------------------
    {
      name: "web",
      testDir: "./web/specs",
      use: {
        baseURL: "http://localhost:5173",
        trace: "retain-on-failure",
        screenshot: "only-on-failure",
        ...devices["Desktop Chrome"],
      },
    },
    // -----------------------------------------------------------------------
    // mcp — cross-process acceptance tests for the MCP gateway
    // No browser needed: tests spawn OS subprocesses (daemon + shim) directly.
    // -----------------------------------------------------------------------
    {
      name: "mcp",
      testDir: "./mcp/specs",
      // No browser; `page` fixture is unavailable in these tests.
    },
  ],
});
