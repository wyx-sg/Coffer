// e2e/playwright.docs.config.ts
//
// Docs images: the pages the docs site shows, on a daemon seeded with demo
// data, written as PNGs into docs-site/public/shots/<lang>/<theme>/. Not a
// test of the UI: nothing is compared, the run writes files. Its own daemon
// (:18200) and Vite (:5175) keep it apart from the functional and visual
// suites. `make docs-shots` regenerates; see
// docs/decisions/docs-screenshots-are-generated-from-a-seeded-daemon.md.
import { defineConfig, devices } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import {
  DOCS_DAEMON_PORT,
  DOCS_HOME,
  DOCS_HOME_FILE,
  DOCS_VITE_PORT,
} from "./docs/env";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const VITE_ORIGIN = `http://localhost:${DOCS_VITE_PORT}`;

export default defineConfig({
  testDir: "./docs/specs",
  outputDir: "./docs/test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  webServer: [
    {
      command: `rm -rf ${DOCS_HOME} && mkdir -p ${DOCS_HOME} && bash ./scripts/start_daemon.sh`,
      url: `http://127.0.0.1:${DOCS_DAEMON_PORT}/api/v1/daemon/status`,
      timeout: 90_000,
      reuseExistingServer: false,
      cwd: __dirname,
      env: {
        COFFER_E2E_HOME: DOCS_HOME,
        COFFER_E2E_HOME_FILE: DOCS_HOME_FILE,
        COFFER_E2E_PORT: String(DOCS_DAEMON_PORT),
        COFFER_DAEMON_EXIT_WITH_PID: String(process.pid),
        COFFER_CORS_ORIGINS: `${VITE_ORIGIN},http://127.0.0.1:${DOCS_VITE_PORT}`,
        // The docs show every page, experimental ones included.
        COFFER_E2E_FEATURES: "knowledge=on,memory=on",
      },
    },
    {
      command: `npm run dev -- --port ${DOCS_VITE_PORT} --strictPort`,
      url: VITE_ORIGIN,
      timeout: 60_000,
      reuseExistingServer: false,
      cwd: path.join(ROOT, "frontend"),
      env: {
        VITE_COFFER_BASE_URL: `http://127.0.0.1:${DOCS_DAEMON_PORT}/api/v1`,
      },
    },
  ],
  projects: [
    {
      name: "docs",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: VITE_ORIGIN,
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
        locale: "en-US",
        timezoneId: "UTC",
      },
    },
  ],
});
