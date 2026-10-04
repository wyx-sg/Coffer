// e2e/visual/env.ts
// Fixed ports and paths shared by playwright.visual.config.ts and its specs.
export const VISUAL_DAEMON_PORT = 18100;
export const VISUAL_VITE_PORT = 5174;
// A fixed HOME, wiped before every run. Fixed (not mktemp) because pages show
// paths under it (data directory, vault root), so a random name would be a
// pixel diff on every run.
export const VISUAL_HOME = "/tmp/coffer-e2e-visual";
export const VISUAL_HOME_FILE = "/tmp/coffer-e2e-visual-home.path";
