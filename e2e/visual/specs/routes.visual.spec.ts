// e2e/visual/specs/routes.visual.spec.ts
//
// Visual baseline: each sidebar route, the Settings modal and its tabs, every agent detail tab, one MCP server open and the Knowledge page with a collection, in light and dark, on a fresh
// daemon, compared against the committed screenshot for this platform.
// The visual daemon pins every experimental feature on (`COFFER_FEATURES`), so the pages of all four are the baselines.
import { expect, test, type Locator, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import { VISUAL_HOME } from "../env";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

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
  {
    name: "usage",
    path: "/model-providers?tab=usage",
    finalPath: /\/model-providers\?tab=usage$/,
  },
  { name: "sync", path: "/sync" },
  // Settings is a modal over the page underneath (Overview on a fresh load).
  { name: "settings", path: "/settings", finalPath: /\/settings\/general$/ },
  { name: "settings-data", path: "/settings/data" },
  { name: "settings-daemon", path: "/settings/daemon" },
  { name: "settings-about", path: "/settings/about" },
  { name: "settings-features", path: "/settings/features" },
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
  /* A scrollbar appears only when a run wrote enough records to overflow. */
  scrollbar-width: none !important;
}
.tsqd-parent-container { display: none !important; }
/* Masked regions whose size follows how many records a run wrote: pin the
   size (a run always writes at least six records) so the layout around them
   is the same in every run. */
/* How many records a run writes varies, so the rows area is one fixed block. */
[data-visual-volatile="rows"] { display: block !important; height: 204px !important; overflow: hidden !important; }
[data-visual-volatile="rows"] > tr { display: none !important; }
[data-visual-volatile="count"] { display: inline-block !important; width: 4ch !important; overflow: hidden !important; vertical-align: middle; }`;

function daemonToken(): string {
  const json = fs.readFileSync(
    path.join(VISUAL_HOME, ".coffer", "daemon.json"),
    "utf-8",
  );
  return (JSON.parse(json) as { token: string }).token;
}

test.beforeEach(async ({ context }) => {
  const token = daemonToken();
  // The daemon's change feed is a stream that never ends, so the page would
  // never reach network idle; refuse it, and the pages fall back to their
  // "not live" mark, the same in every run.
  await context.route("**/api/v1/events", (route) => route.abort());
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
    // Records and counts that differ from one fresh daemon to the next (the
    // daemon's own log lines, how many were written) — marked by the page.
    page.locator("[data-visual-volatile]"),
    // Dates as the UI formats them ("30 Sep 2026", "Sep 30, 2026").
    page.getByText(
      /\b(\d{1,2} [A-Z][a-z]{2} \d{4}|[A-Z][a-z]{2} \d{1,2}, \d{4})\b/,
    ),
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
    fs.writeFileSync(path.join(bin, name), `#!/bin/sh\necho "${version}"\n`, {
      mode: 0o755,
    });
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
    const json = fs.readFileSync(
      path.join(VISUAL_HOME, ".coffer", "daemon.json"),
      "utf-8",
    );
    const { token, port } = JSON.parse(json) as { token: string; port: number };
    const headers = {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
    };
    const listed = await fetch(`http://127.0.0.1:${port}/api/v1/agents/types`, {
      headers,
    });
    const { types } = (await listed.json()) as {
      types: { type: string; uid: string | null }[];
    };
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
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        await page.goto(`/agents/claude_code${suffix}`);
        await expect(page).toHaveURL(
          new RegExp(`/agents/claude_code${suffix}$`),
        );
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(page.getByRole("tab")).toHaveCount(6);
        await settle(page);
        await expect(page).toHaveScreenshot(`agent-${tab}-${theme}.png`, {
          fullPage: false,
          mask: [...timeDependent(page), ...runDependent(page)],
        });
      });
    }
  }
});

/**
 * The Knowledge page with a collection in it: its overview, an open document,
 * the document's History tab and Recent changes. Submitted items are written
 * as documents on the spot, so the pages read the same on every machine.
 */
test.describe("knowledge collection", () => {
  let uid = "";
  const collection = "visual-notes";
  const document = `${collection}/daemon-port.md`;

  test.beforeAll(async () => {
    const json = fs.readFileSync(
      path.join(VISUAL_HOME, ".coffer", "daemon.json"),
      "utf-8",
    );
    const { token, port } = JSON.parse(json) as { token: string; port: number };
    const base = `http://127.0.0.1:${port}/api/v1/knowledge`;
    const headers = {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
    };
    const listed = await fetch(`${base}/collections`, { headers });
    const { collections } = (await listed.json()) as {
      collections: { uid: string; name: string }[];
    };
    const existing = collections.find((c) => c.name === collection);
    if (existing) {
      uid = existing.uid;
      return;
    }
    const created = await fetch(`${base}/collections`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        name: collection,
        description: "How the daemon and its shim fit together.",
      }),
    });
    expect(created.status).toBe(201);
    uid = ((await created.json()) as { uid: string }).uid;
    for (const [title, body] of [
      [
        "Daemon port",
        "# Daemon port\n\nThe daemon binds one fixed port, read before the database opens.\n\n## Startup\n\n- The shell waits for the health check.\n",
      ],
      [
        "Vault sync",
        "# Vault sync\n\nA sync round takes the vault lock; a write waits for it.\n",
      ],
    ]) {
      // Submitted as the page's Upload does: one Markdown file per document.
      const form = new FormData();
      form.set("collection", collection);
      form.set(
        "file",
        new Blob([body], { type: "text/markdown" }),
        `${title.toLowerCase().replaceAll(" ", "-")}.md`,
      );
      const res = await fetch(`${base}/upload`, {
        method: "POST",
        headers: { "X-Coffer-Token": headers["X-Coffer-Token"] },
        body: form,
      });
      expect(res.ok).toBe(true);
    }
  });

  const VIEWS: [string, () => string][] = [
    ["knowledge-collection", () => `/knowledge/${uid}`],
    [
      "knowledge-document",
      () => `/knowledge/${uid}?file=${encodeURIComponent(document)}`,
    ],
    [
      "knowledge-history",
      () => `/knowledge/${uid}/history?file=${encodeURIComponent(document)}`,
    ],
    ["knowledge-recent", () => "/knowledge"],
  ];

  for (const [name, address] of VIEWS) {
    for (const theme of THEMES) {
      test(`${name} (${theme})`, async ({ page }) => {
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        await page.goto(address());
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(
          page.getByRole("navigation", { name: "Collections and documents" }),
        ).toBeVisible();
        await settle(page);
        await expect(page).toHaveScreenshot(`${name}-${theme}.png`, {
          fullPage: false,
          mask: [...timeDependent(page), ...runDependent(page)],
        });
      });
    }
  }
});

/**
 * One MCP server open on the MCP servers page: its Overview and its Tools tab.
 * The server is the suite's fake stdio server; a test in beforeAll records it
 * healthy and discovery lists its tools, so the page reads the same every run.
 */
test.describe("mcp server", () => {
  const name = "visual-files";

  test.beforeAll(async () => {
    const json = fs.readFileSync(
      path.join(VISUAL_HOME, ".coffer", "daemon.json"),
      "utf-8",
    );
    const { token, port } = JSON.parse(json) as { token: string; port: number };
    const base = `http://127.0.0.1:${port}/api/v1`;
    const headers = {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
    };
    const root = REPO_ROOT;
    const listed = await fetch(`${base}/resources?kind=mcp_server`, {
      headers,
    });
    const { resources } = (await listed.json()) as {
      resources: { uid: string; name: string }[];
    };
    let uid = resources.find((r) => r.name === name)?.uid;
    if (!uid) {
      const created = await fetch(`${base}/resources`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          kind: "mcp_server",
          name,
          config: {
            transport: {
              type: "stdio",
              command: path.join(root, ".venv/bin/python3"),
              args: [
                path.join(root, "backend/tests/fixtures/fake_mcp_server.py"),
                "--scenario",
                "basic",
                "--tools",
                "read_file",
                "write_file",
                "list_directory",
              ],
            },
          },
        }),
      });
      expect(created.status).toBe(201);
      uid = ((await created.json()) as { uid: string }).uid;
    }
    expect(
      (
        await fetch(`${base}/resources/mcp_server/${uid}/test`, {
          method: "POST",
          headers,
        })
      ).ok,
    ).toBe(true);
    expect(
      (
        await fetch(`${base}/resources/mcp_server/${uid}/refresh`, {
          method: "POST",
          headers,
        })
      ).ok,
    ).toBe(true);
  });

  for (const [tab, suffix] of [
    ["overview", ""],
    ["tools", "/tools"],
  ] as const) {
    for (const theme of THEMES) {
      test(`mcp-server-${tab} (${theme})`, async ({ page }) => {
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        await page.goto(`/mcp-servers/${name}${suffix}`);
        await expect(page).toHaveURL(
          new RegExp(`/mcp-servers/${name}${suffix}$`),
        );
        await expect(page.getByTestId("mcp-server-pane")).toBeVisible();
        await expect(
          page.getByText("read_file", { exact: true }).first(),
        ).toBeVisible();
        await settle(page);
        await expect(page).toHaveScreenshot(`mcp-server-${tab}-${theme}.png`, {
          fullPage: false,
          mask: [...timeDependent(page), ...runDependent(page)],
        });
      });
    }
  }
});
