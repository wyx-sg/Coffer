// e2e/docs/env.ts
// Fixed ports and paths shared by playwright.docs.config.ts and its specs.
export const DOCS_DAEMON_PORT = 18200;
export const DOCS_VITE_PORT = 5175;
// A fixed HOME, wiped before every run, so pages that show a path under it
// show the same one each time.
export const DOCS_HOME = "/tmp/coffer-e2e-docs";
export const DOCS_HOME_FILE = "/tmp/coffer-e2e-docs-home.path";
