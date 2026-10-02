// e2e/playwright.visual.config.ts
//
// Visual baseline: every top-level route, light and dark, compared against a
// committed screenshot. Separate from playwright.config.ts so it gets its own
// daemon (fresh HOME, port 18100) and its own Vite (5174): nothing the
// functional suite creates can leak into the pixels, and the two suites can
// run side by side. `make verify-visual` compares, `make visual-update`
// re-records; see .agents/testing.md "Visual baseline".
import { defineConfig, devices } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import {
  VISUAL_DAEMON_PORT,
  VISUAL_HOME,
  VISUAL_HOME_FILE,
  VISUAL_VITE_PORT,
} from "./visual/env";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const VITE_ORIGIN = `http://localhost:${VISUAL_VITE_PORT}`;

export default defineConfig({
  testDir: "./visual/specs",
  // Not the default ./test-results: Playwright empties its outputDir on start,
  // and the functional suite's failure traces (./test-results) must survive
  // for the artifact upload when both run on one machine (`make verify-all`).
  outputDir: "./visual/test-results",
  // {platform} keeps darwin and linux baselines side by side: font rasterising
  // differs between them, so one platform's image can never pass on the other.
  snapshotPathTemplate: "{testDir}/__screenshots__/{platform}/{arg}{ext}",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  // A retry would hide exactly the nondeterminism this suite exists to catch.
  retries: 0,
  reporter: [["list"]],
  // Locally a missing baseline fails (record it deliberately with
  // `make visual-update`). In CI a platform with no baseline yet — linux, until
  // someone commits it — is WRITTEN and uploaded as an artifact instead of
  // failing, so nothing is compared there (the CI job is report-only for that
  // reason); once the images are committed they are compared.
  updateSnapshots: process.env.CI ? "missing" : "none",

  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      scale: "css",
      // Same platform, same pinned Chromium, fonts bundled with the app, so a
      // rerun is pixel-identical (measured: 0 differing pixels across runs).
      // The budget exists only to absorb anti-aliasing jitter on glyph edges
      // (a GPU / driver change on a dev Mac): 0.1% of 1280x800 is ~1,000
      // pixels, while `threshold` (per-pixel colour distance, default 0.2)
      // already ignores sub-perceptual shade drift. A real change — a moved
      // control, a recoloured surface, a different font — costs far more.
      maxDiffPixelRatio: 0.001,
    },
  },

  webServer: [
    {
      // Fresh daemon every run — never reused, so no state from a previous run
      // (or from the functional suite's daemon on 18000) shows up.
      command: `rm -rf ${VISUAL_HOME} && mkdir -p ${VISUAL_HOME} && bash ./scripts/start_daemon.sh`,
      url: `http://127.0.0.1:${VISUAL_DAEMON_PORT}/api/v1/daemon/status`,
      timeout: 90_000,
      reuseExistingServer: false,
      cwd: __dirname,
      env: {
        COFFER_E2E_HOME: VISUAL_HOME,
        COFFER_E2E_HOME_FILE: VISUAL_HOME_FILE,
        COFFER_E2E_PORT: String(VISUAL_DAEMON_PORT),
        // start_daemon.sh's COFFER_DEV_CORS only allows :5173; this list
        // replaces it with the visual Vite origin.
        COFFER_CORS_ORIGINS: `${VITE_ORIGIN},http://127.0.0.1:${VISUAL_VITE_PORT}`,
      },
    },
    {
      command: `npm run dev -- --port ${VISUAL_VITE_PORT} --strictPort`,
      url: VITE_ORIGIN,
      timeout: 60_000,
      reuseExistingServer: false,
      cwd: path.join(ROOT, "frontend"),
      env: {
        VITE_COFFER_BASE_URL: `http://127.0.0.1:${VISUAL_DAEMON_PORT}/api/v1`,
      },
    },
  ],

  projects: [
    {
      name: "visual",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: VITE_ORIGIN,
        viewport: { width: 1280, height: 800 },
        deviceScaleFactor: 1,
        locale: "en-US",
        timezoneId: "UTC",
        trace: "retain-on-failure",
      },
    },
  ],
});
