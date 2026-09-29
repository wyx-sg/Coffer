// e2e/visual/specs/routes.visual.spec.ts
//
// Visual baseline: each sidebar route, the Settings modal and every agent detail tab, in light and dark, on a fresh
// daemon, compared against the committed screenshot for this platform.
// Pages behind an experimental gate render their gate notice — that notice is
// the baseline for them until the feature is on by default.
import { expect, test, type Locator, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

import { VISUAL_HOME } from "../env";

type Theme = "light" | "dark";

interface RouteCase {
  /** Snapshot name stem. */
  name: string;
  path: string;
  /** Where the page settles; checked before shooting. Defaults to "/"+name. */
  finalPath?: RegExp;
}

const ROUTES: RouteCase[] = [
  { name: "overview", path: "/", finalPath: /\/$/ },
  { name: "agents", path: "/agents" },
  { name: "model-providers", path: "/model-providers" },
  { name: "conversations", path: "/conversations" },
  { name: "channels", path: "/channels" },
  { name: "mcp-servers", path: "/mcp-servers" },
  { name: "custom-tools", path: "/custom-tools" },
  { name: "skills", path: "/skills" },
  { name: "clis", path: "/clis" },
  { name: "knowledge", path: "/knowledge" },
  { name: "memory", path: "/memory" },
  { name: "secrets", path: "/secrets" },
  { name: "activity", path: "/activity" },
  { name: "usage", path: "/usage" },
  { name: "sync", path: "/sync" },
  // Settings is a modal over the page underneath (Overview on a fresh load).
  { name: "settings", path: "/settings", finalPath: /\/settings\/general$/ },
];

const THEMES: Theme[] = ["light", "dark"];

// Belt-and-braces on top of `animations: "disabled"`: no pulse, no spinner,
// no transition mid-flight, no blinking caret. Also hides the TanStack Query
// devtools button, which only the Vite dev server renders (main.tsx gates it
// on import.meta.env.DEV) — it is not part of the product.
const FREEZE_CSS = `*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
.tsqd-parent-container { display: none !important; }`;

function daemonToken(): string {
  const json = fs.readFileSync(
    path.join(VISUAL_HOME, ".coffer", "daemon.json"),
    "utf-8",
  );
  return (JSON.parse(json) as { token: string }).token;
}

test.beforeEach(async ({ context }) => {
  const token = daemonToken();
  // An init script, not page.addStyleTag: the Vite dev server reloads the page
  // once when it first optimises dependencies, and a tag added after goto
  // would be gone after that reload.
  await context.addInitScript((css: string) => {
    const add = () => {
      const style = document.createElement("style");
      style.textContent = css;
      document.head.appendChild(style);
    };
    if (document.head) add();
    else document.addEventListener("DOMContentLoaded", add, { once: true });
  }, FREEZE_CSS);
  await context.addInitScript((tok: string) => {
    (window as unknown as { __COFFER_TOKEN__?: string }).__COFFER_TOKEN__ = tok;
    // Pin the UI language (the detector reads this key before navigator) and
    // leave the theme on "system" so emulateMedia decides it.
    try {
      localStorage.setItem("coffer.language", "en");
      localStorage.removeItem("coffer.theme");
    } catch {
      /* storage blocked: navigator (en-US) still wins */
    }
  }, token);
});

/** Text that changes with the clock, never with the design. */
function timeDependent(page: Page): Locator[] {
  return [
    page.locator("time"),
    page.getByText(
      /\b(just now|\d+\s?(s|m|h|d|sec|min|mins|minutes?|hours?|days?) ago)\b/i,
    ),
    page.getByText(/\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/),
    page.getByText(/\b\d{1,2}:\d{2}(:\d{2})?\s?(AM|PM)?\b/),
    page.getByText(/\buptime\b/i),
    // Dates as the UI formats them ("30 Sep 2026", "Sep 30, 2026").
    page.getByText(/\b(\d{1,2} [A-Z][a-z]{2} \d{4}|[A-Z][a-z]{2} \d{1,2}, \d{4})\b/),
  ];
}

/** Text that changes with the machine or the run, never with the design. */
function runDependent(page: Page): Locator[] {
  return [
    // An installed program's version ("v2.1.281", "Installed · v0.41.0").
    // Exactly three parts, so an address like 127.0.0.1 is not taken for one.
    page.getByText(/(?<![\d.])v?\d+\.\d+\.\d+(?![.\d])/),
    // A uid minted by this run's daemon (32 hex digits).
    page.getByText(/^[0-9a-f]{32}$/),
    // A date on its own ("Registered 2026-09-29").
    page.getByText(/^\d{4}-\d{2}-\d{2}$/),
  ];
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  const main = page.locator("main#main");
  await expect(main).toBeVisible();
  // Loading placeholders and spinners gone.
  await expect(main.locator(".animate-pulse")).toHaveCount(0);
  await expect(page.locator(".animate-spin")).toHaveCount(0);
  // The bundled faces are in, not the fallback.
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.fonts.check("13px Figtree"))).toBe(
    true,
  );
  await page.waitForLoadState("networkidle");
}

/**
 * Stand-in `claude` and `codex` programs in the visual HOME's `bin`, which
 * start_daemon.sh puts first on the daemon's PATH, so both agents read as
 * installed (never run) on every machine — a real install would make the
 * Agents page differ between a dev Mac and CI.
 */
test.beforeAll(() => {
  const bin = path.join(VISUAL_HOME, "bin");
  fs.mkdirSync(bin, { recursive: true });
  const programs: Record<string, string> = {
    claude: "2.1.281 (Claude Code)",
    codex: "codex-cli 0.41.0",
  };
  for (const [name, version] of Object.entries(programs)) {
    fs.writeFileSync(path.join(bin, name), `#!/bin/sh\necho "${version}"\n`, { mode: 0o755 });
  }
});

for (const route of ROUTES) {
  for (const theme of THEMES) {
    test(`${route.name} (${theme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.goto(route.path);

      await expect(page).toHaveURL(
        route.finalPath ?? new RegExp(`${route.path}$`),
      );
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await settle(page);

      await expect(page).toHaveScreenshot(`${route.name}-${theme}.png`, {
        fullPage: false,
        mask: [...timeDependent(page), ...runDependent(page)],
      });
    });
  }
}

/** The agent detail page, one route per tab, for a Claude Code agent added on the fresh daemon. */
const AGENT_TABS = [
  ["overview", ""],
  ["model", "/model"],
  ["skills", "/skills"],
  ["mcp-servers", "/mcp-servers"],
  ["plugins", "/plugins"],
  ["hooks", "/hooks"],
  ["config", "/config"],
  ["memory", "/memory"],
  ["sessions", "/sessions"],
] as const;

test.describe("agent detail", () => {
  test.beforeAll(async () => {
    const json = fs.readFileSync(path.join(VISUAL_HOME, ".coffer", "daemon.json"), "utf-8");
    const { token, port } = JSON.parse(json) as { token: string; port: number };
    const headers = { "Content-Type": "application/json", "X-Coffer-Token": token };
    const listed = await fetch(`http://127.0.0.1:${port}/api/v1/agents/types`, { headers });
    const { types } = (await listed.json()) as { types: { type: string; uid: string | null }[] };
    if (types.some((row) => row.type === "claude_code" && row.uid)) return;
    const created = await fetch(`http://127.0.0.1:${port}/api/v1/agents`, {
      method: "POST",
      headers,
      body: JSON.stringify({ type: "claude_code" }),
    });
    expect(created.status).toBe(201);
  });

  for (const [tab, suffix] of AGENT_TABS) {
    for (const theme of THEMES) {
      test(`agent-${tab} (${theme})`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.goto(`/agents/claude_code${suffix}`);
        await expect(page).toHaveURL(new RegExp(`/agents/claude_code${suffix}$`));
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(page.getByRole("tab")).toHaveCount(9);
        await settle(page);
        await expect(page).toHaveScreenshot(`agent-${tab}-${theme}.png`, {
          fullPage: false,
          mask: [...timeDependent(page), ...runDependent(page)],
        });
      });
    }
  }
});
