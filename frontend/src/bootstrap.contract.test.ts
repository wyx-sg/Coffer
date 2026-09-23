/**
 * A source-level guard on one property of `main.tsx` that no behavioural test
 * can reach: the desktop credential handshake must not hold up the first paint.
 *
 * `main.tsx` renders as a side effect of being imported, so a test cannot mount
 * it and observe ordering without mounting the whole application — and the
 * regression this guards is invisible in a browser, where the handshake does
 * not exist. It only shows up inside the Tauri shell, on a cold start, as an
 * empty window for as long as spawning a daemon takes (`get_daemon_info`'s
 * poll deadline, and then every retry after it).
 *
 * The tempting change is real: firing queries before the connection lands means
 * they come back `DAEMON_NOT_READY` for a moment, and `await`ing the handshake
 * makes that flicker go away. It buys the flicker with the blank window, which
 * is the worse trade and the one spec desktop-app rules out ("Host the UI locally
 * in an application window", "Supply the page its daemon connection over IPC") — and
 * the handshake now retries until it lands, so awaiting it can block the paint
 * for as long as the daemon stays down, i.e. forever.
 *
 * Reading the source is unusual for a frontend test; it is how the repo already
 * pins release-pipeline invariants whose feedback loop is too long to rely on
 * (see backend/tests/integration/distribution/test_packaging_specs.py).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect } from "vitest";
import { acceptance } from "@/test/acceptance";

// Resolved from the Vitest root (frontend/) rather than `import.meta.url`,
// which the test transform does not leave as a file: URL.
const MAIN = readFileSync(resolve(process.cwd(), "src/main.tsx"), "utf-8");

describe("main.tsx bootstrap", () => {
  acceptance("desktop-app", "the window waits for a daemon, and opens either way", () => {
    // The call must exist — otherwise the desktop host never gets a token.
    expect(MAIN).toContain("credentialDesktopHost");

    const started = MAIN.indexOf("credentialDesktopHost(");
    const rendered = MAIN.indexOf("createRoot");
    expect(started).toBeGreaterThan(-1);
    expect(rendered).toBeGreaterThan(-1);
    // Started before the render, so a daemon that is already up credentials
    // the very first queries…
    expect(started).toBeLessThan(rendered);

    // …but never awaited: it retries until a daemon answers, so awaiting it
    // would hold the paint for as long as the daemon stays down.
    expect(MAIN).not.toMatch(/await\s+credentialDesktopHost\s*\(/);
    expect(MAIN).not.toMatch(/await\s+connectToShellDaemon\s*\(/);
  });

  acceptance("desktop-app", "the window waits for a daemon, and opens either way", () => {
    // Queries that went out before the connection arrived hold a
    // DAEMON_NOT_READY that nothing else clears; the invalidate is the repair,
    // not a nicety. It is what `credentialDesktopHost` is handed to run.
    expect(MAIN).toMatch(/invalidateQueries\(\)/);
  });
});
