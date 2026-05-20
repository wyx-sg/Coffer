import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 1 : undefined,
  reporter: isCI ? "github" : "list",

  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: [
    {
      command: "../.venv/bin/uvicorn coffer.main:app --port 8000",
      cwd: "../backend",
      port: 8000,
      reuseExistingServer: !isCI,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      cwd: "../frontend",
      port: 5173,
      reuseExistingServer: !isCI,
      timeout: 30_000,
    },
  ],
});
