/// <reference types="vitest" />
import * as fs from "node:fs";
import * as os from "node:os";
import path from "node:path";
import { defineConfig, type PluginOption } from "vite";
import react from "@vitejs/plugin-react";

// Vite + Tauri 2 conventions:
//   - clearScreen: false        keep Tauri's terminal output visible
//   - server.strictPort: true   Tauri expects a known port
//   - envPrefix: ["VITE_", "TAURI_ENV_*"]  let Tauri inject build-time env
//
// `TAURI_DEV_HOST` is set by `tauri dev` when running on a remote host
// (mobile dev). Falls back to localhost for browser-only dev.
const host = process.env.TAURI_DEV_HOST;

/**
 * Dev-only plugin that reads ~/.coffer/daemon.json on each request and
 * injects the active token + base URL into index.html, so that opening
 * `npm run dev` in a real browser (no Tauri) is immediately authenticated.
 *
 * Without this, the FE would get null from getCofferToken() in browser
 * dev mode (Tauri injects __COFFER_TOKEN__ in the desktop shell, but the
 * browser path has no equivalent), and every API call would 401.
 *
 * Skipped entirely when VITE_COFFER_BASE_URL is set in env — that's the
 * signal that a managed test runner (Playwright e2e) owns the base URL
 * and token (via addInitScript). Without this guard the plugin would
 * happily read a stale user-home daemon.json from a previous local dev
 * session and pollute the e2e environment with the wrong port.
 *
 * Only runs under `vite dev` — the production / Tauri build never touches
 * the user's daemon.json. Safe because Vite's dev server already binds
 * loopback by default and only serves to the local host.
 */
function cofferDevTokenInjection(): PluginOption {
  const daemonJsonPath = path.join(os.homedir(), ".coffer", "daemon.json");
  const externallyManaged = !!process.env.VITE_COFFER_BASE_URL;

  function readToken(): { token: string; port: number } | null {
    try {
      const raw = fs.readFileSync(daemonJsonPath, "utf-8");
      const parsed = JSON.parse(raw) as { token?: string; port?: number };
      if (typeof parsed.token === "string" && typeof parsed.port === "number") {
        return { token: parsed.token, port: parsed.port };
      }
    } catch {
      // daemon.json missing or unreadable; FE will fall back to empty token
      // and show the UNAUTHENTICATED error envelope, which is the correct
      // user-facing signal for "start the daemon".
    }
    return null;
  }

  return {
    name: "coffer-dev-token-injection",
    apply: "serve",
    configureServer(server) {
      // When externally managed (e2e Playwright), do not touch the watcher
      // so the test runner's URL/token is never overridden by a stale
      // daemon.json from a previous local dev session.
      if (externallyManaged) return;

      // Tell Vite to watch daemon.json even though it lives outside the
      // project root (it's in $HOME/.coffer/).
      server.watcher.add(daemonJsonPath);

      // Full-reload whenever daemon.json appears, changes, or disappears.
      // The next load re-runs transformIndexHtml, which picks up the new
      // token + port and injects them — so the banner auto-dismisses once
      // the daemon is (re-)started, with no manual page refresh needed.
      const reload = (filePath: string) => {
        if (filePath !== daemonJsonPath) return;
        server.ws.send({ type: "full-reload" });
      };
      server.watcher.on("add", reload);
      server.watcher.on("change", reload);
      server.watcher.on("unlink", reload);
    },
    transformIndexHtml: {
      order: "pre",
      handler() {
        if (externallyManaged) {
          return undefined;
        }
        const info = readToken();
        if (!info) {
          // Emit a comment so the dev knows why auth is failing without
          // needing to grep the source.
          return [
            {
              tag: "script",
              children:
                'console.warn("[coffer-dev] ~/.coffer/daemon.json not found — start the daemon to authenticate.");',
              injectTo: "head",
            },
          ];
        }
        const baseUrl = `http://127.0.0.1:${info.port}/api/v1`;
        return [
          {
            tag: "script",
            children:
              `window.__COFFER_TOKEN__=${JSON.stringify(info.token)};` +
              `window.__COFFER_BASE_URL__=${JSON.stringify(baseUrl)};`,
            injectTo: "head-prepend",
          },
        ];
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), cofferDevTokenInjection()],
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
      ignored: ["**/desktop/**"],
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      // v8 is the default vitest provider and matches the current
      // @vitest/coverage-v8 dev dependency. Reporters: text for local
      // CLI feedback, html for the file://coverage/index.html drill-down,
      // lcov so external tooling (codecov etc.) can ingest it.
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      // Thresholds are pinned slightly below the latest achieved
      // numbers (~87% statements/lines, ~78% branches/functions) so
      // routine churn doesn't trip the gate, but a real regression
      // (e.g., a new uncovered page) is caught before merge. Bump
      // these in lockstep with the actual numbers as coverage grows.
      thresholds: {
        lines: 85,
        functions: 75,
        branches: 75,
        statements: 85,
      },
    },
  },
});
