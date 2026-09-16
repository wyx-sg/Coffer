/**
 * A source-level guard on one property of `main.tsx` that no behavioural test
 * can reach: the desktop credential handshake must not hold up the first paint.
 *
 * `main.tsx` renders as a side effect of being imported, so a test cannot mount
 * it and observe ordering without mounting the whole application — and the
 * regression this guards is invisible in a browser, where the handshake does
 * not exist. It only shows up inside the Tauri shell, on a cold start, as an
 * empty window for as long as spawning a daemon takes (up to fifteen seconds,
 * per `get_daemon_info`'s poll deadline).
 *
 * The tempting change is real: firing queries before the token lands means they
 * come back `UNAUTHENTICATED` for a moment, and `await`ing the handshake makes
 * that flicker go away. It buys the flicker with the blank window, which is the
 * worse trade and the one spec desktop-app FR-001/FR-004 rule out.
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
  acceptance("desktop-app", "the window renders before the daemon answers", () => {
    // The call must exist — otherwise the desktop host never gets a token.
    expect(MAIN).toContain("connectToShellDaemon");

    const call = MAIN.slice(MAIN.indexOf("connectToShellDaemon("));
    const rendered = MAIN.indexOf("createRoot");
    expect(rendered).toBeGreaterThan(-1);

    // `await connectToShellDaemon()` is the specific regression: it makes the
    // render wait on a call that spawns a daemon and polls for it.
    expect(MAIN).not.toMatch(/await\s+connectToShellDaemon\s*\(/);
    // …and so is awaiting it through the helper that wraps it.
    expect(MAIN).not.toMatch(/await\s+credentialDesktopHost\s*\(/);

    // The handshake has to be chained, not awaited, for its result to be
    // installed at all.
    expect(call).toMatch(/\.then\(/);
  });

  acceptance("desktop-app", "the window renders before the daemon answers", () => {
    // Queries that went out before the token arrived hold a 401 that nothing
    // else clears; the invalidate is the repair, not a nicety.
    expect(MAIN).toMatch(/invalidateQueries\(\)/);
  });
});
