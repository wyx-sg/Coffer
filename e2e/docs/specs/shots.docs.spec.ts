// e2e/docs/specs/shots.docs.spec.ts
//
// One scenario per docs image: open the page on the seeded daemon and write an
// image for each language and theme into docs-site/public/shots/. The list below
// is the whole set; a page is added here only when a reader needs to find
// something on screen. `manifest.json` beside the images records each one's
// size, so a page reserves its space before the image loads.
import { expect, test, type Locator, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import { DOCS_DAEMON_PORT, DOCS_HOME } from "../env";
import { seedDemoWorkspace } from "../seed";

const OUT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../docs-site/public/shots",
);

const LANGS = ["en", "zh"] as const;
const THEMES = ["light", "dark"] as const;

interface Shot {
  /** The file name stem, and what pages refer to. */
  name: string;
  route: string;
  /** What shows the page has settled with its data in. */
  ready: (page: Page) => Promise<void>;
  /**
   * `window` (default) is the whole app at 1440x900, for the home page. `panel`
   * is the page area alone at 1040x680, which a guide's column shows at a size
   * the text can still be read at.
   */
  frame?: "window" | "panel";
  /** Get the page into the state the picture shows, such as selecting a row. */
  prepare?: (page: Page) => Promise<void>;
  /** Do something on the page, such as opening a dialog; the dialog is the picture. */
  open?: (page: Page) => Promise<Locator>;
}

const PANEL = { width: 1040, height: 680 };
const WINDOW = { width: 1440, height: 900 };

const heading = (re: RegExp) => async (page: Page) => {
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await expect(page.locator("main#main")).toContainText(re);
};

// The server's own tools are listed once the daemon has connected to it.
const serverTested = async (page: Page) => {
  await page.getByRole("button", { name: /^(Test|测试)$/ }).click();
  await expect(page.locator("main#main")).toContainText(
    "Open an issue in a repository.",
    { timeout: 20_000 },
  );
};

const skillOpen = async (page: Page) => {
  await expect(
    page.getByRole("heading", { level: 2, name: "gh-triage" }).first(),
  ).toBeVisible();
  await expect(page.locator("main#main")).toContainText(
    "Sort new GitHub issues by area and urgency.",
  );
};

// The home page's tabs: one whole-window picture per sidebar page, in sidebar
// order. Pages that are lists open on their first row, so the picture shows the
// page doing its work.
const HOME: Array<
  [
    string,
    string,
    (page: Page) => Promise<void>,
    ((page: Page) => Promise<void>)?,
  ]
> = [
  ["overview", "/", heading(/sentry/)],
  ["agents", "/agents/claude_code", heading(/Claude Code/)],
  ["model-providers", "/model-providers", heading(/./)],
  ["conversations", "/conversations", heading(/./)],
  ["channels", "/channels", heading(/./)],
  ["mcp-servers", "/mcp-servers/github", serverTested],
  ["custom-tools", "/custom-tools/orders-api", heading(/orders-api/)],
  ["skills", "/skills/gh-triage", skillOpen],
  ["clis", "/clis", heading(/./)],
  [
    "knowledge",
    "/knowledge",
    heading(/engineering/),
    async (page) => {
      await page.getByText("engineering", { exact: true }).first().click();
      await page
        .getByText("deploy-checklist", { exact: false })
        .first()
        .click();
      await expect(page.locator("main#main")).toContainText(
        "Run the migrations",
      );
    },
  ],
  ["memory", "/memory", heading(/./)],
  [
    "secrets",
    "/secrets",
    heading(/./),
    async (page) => {
      await page.getByText("LINEAR_API_KEY", { exact: true }).first().click();
      await expect(page.locator("main#main")).not.toContainText(
        "Nothing selected",
      );
    },
  ],
  ["activity", "/activity", heading(/./)],
  ["sync", "/sync", heading(/./)],
  [
    "settings",
    "/settings/general",
    heading(/./),
    async (page) => {
      // Keep the close button's tooltip out of the picture.
      await page
        .getByRole("dialog")
        .getByRole("heading", { level: 2 })
        .first()
        .click();
    },
  ],
];

export const SHOTS: Shot[] = [
  ...HOME.map(
    ([id, route, ready, prepare]): Shot => ({
      name: `home-${id}`,
      route,
      ready,
      prepare,
    }),
  ),

  // Guide pictures: the page area, or the dialog a step opens.
  {
    name: "agents-list",
    route: "/agents",
    frame: "panel",
    ready: heading(/Claude Code/),
  },
  {
    name: "agent-page",
    route: "/agents/claude_code",
    frame: "panel",
    ready: heading(/Claude Code/),
  },
  {
    name: "connect-dialog",
    route: "/agents",
    ready: heading(/Codex/),
    open: async (page) => {
      await page.getByRole("button", { name: /^(Connect|连接)$/ }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      return dialog;
    },
  },
  {
    name: "mcp-server",
    route: "/mcp-servers/github",
    frame: "panel",
    ready: serverTested,
  },
  {
    name: "add-server-dialog",
    route: "/mcp-servers",
    ready: heading(/github/),
    open: async (page) => {
      await page
        .getByRole("button", { name: /^(Add server|添加服务器)$/ })
        .click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      return dialog;
    },
  },
  {
    name: "providers",
    route: "/model-providers",
    frame: "panel",
    ready: heading(/./),
  },
  {
    name: "add-provider-dialog",
    route: "/model-providers",
    ready: heading(/./),
    open: async (page) => {
      await page
        .getByRole("button", { name: /^(Add provider|添加提供商)$/ })
        .first()
        .click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      return dialog;
    },
  },
  {
    name: "skill",
    route: "/skills/gh-triage",
    frame: "panel",
    ready: skillOpen,
  },
  {
    name: "conversations",
    route: "/conversations",
    frame: "panel",
    ready: heading(/./),
  },
  { name: "channels", route: "/channels", frame: "panel", ready: heading(/./) },
  {
    name: "knowledge-page",
    route: "/knowledge",
    frame: "panel",
    ready: heading(/engineering/),
  },
  { name: "secrets", route: "/secrets", frame: "panel", ready: heading(/./) },
];

const FREEZE_CSS = `*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
  scrollbar-width: none !important;
}
.tsqd-parent-container { display: none !important; }
/* A toast left by the last action, such as "Test passed". */
[role="status"]:has([data-testid="toast-timer"]) { display: none !important; }`;

function daemonToken(): string {
  const json = fs.readFileSync(
    path.join(DOCS_HOME, ".coffer", "daemon.json"),
    "utf-8",
  );
  return (JSON.parse(json) as { token: string }).token;
}

/**
 * Re-encode a PNG as WebP with the browser's own encoder, so the run needs no
 * image library and a committed picture is about a third of the PNG's size.
 */
async function toWebp(page: Page, png: Buffer): Promise<Buffer> {
  const base64 = await page.evaluate(async (b64: string) => {
    const bitmap = await createImageBitmap(
      await (await fetch(`data:image/png;base64,${b64}`)).blob(),
    );
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0);
    const blob = await canvas.convertToBlob({
      type: "image/webp",
      quality: 0.92,
    });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
  }, png.toString("base64"));
  return Buffer.from(base64, "base64");
}

/**
 * The page area below the title strip. The strip is the window's, not the
 * page's, so a picture of the page leaves it out.
 */
async function panelBox(page: Page) {
  const box = await page.locator("main#main").boundingBox();
  if (!box) throw new Error("main#main has no box");
  const inset = await page.evaluate(() =>
    parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue(
        "--titlebar-inset",
      ),
    ),
  );
  // End the picture a little below the page's last content, so a short page
  // is not followed by a blank half; elements that stretch to the window's
  // bottom (a full-height pane) do not count.
  const bottom = await page.evaluate(() => {
    const main = document.querySelector("main#main")!;
    const top = main.getBoundingClientRect().top;
    const full = main.getBoundingClientRect().height * 0.9;
    let last = 0;
    for (const el of main.querySelectorAll("*")) {
      const r = el.getBoundingClientRect();
      if (r.height > 0 && r.width > 0 && r.height < full) {
        last = Math.max(last, r.bottom - top);
      }
    }
    return last;
  });
  const height = Math.min(
    box.height - inset,
    Math.max(bottom - inset + 32, 240),
  );
  return { x: box.x, y: box.y + inset, width: box.width, height };
}

/**
 * The three lights macOS draws over the app's title strip. They belong to the
 * system, not the page, so a browser capture has none; these sit where the
 * strip reserves room for them (14px frames, 20px apart, from x 20, centred on
 * y 19).
 */
async function addTrafficLights(page: Page): Promise<void> {
  await page.evaluate(() => {
    const colours = ["#ff5f57", "#febc2e", "#28c840"];
    colours.forEach((colour, i) => {
      const light = document.createElement("div");
      light.setAttribute("aria-hidden", "true");
      light.style.cssText = `position:fixed;z-index:99999;top:13px;left:${21 + i * 20}px;width:12px;height:12px;border-radius:50%;background:${colour};box-shadow:inset 0 0 0 0.5px rgba(0,0,0,.18)`;
      document.body.appendChild(light);
    });
  });
}

/** Width and height from a PNG's header. */
function pngSize(png: Buffer): [number, number] {
  return [png.readUInt32BE(16), png.readUInt32BE(20)];
}

const sizes: Record<string, [number, number]> = {};

test.afterAll(() => {
  const file = path.join(OUT, "manifest.json");
  let known: Record<string, [number, number]> = {};
  try {
    known = JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch {
    /* no manifest yet */
  }
  // Merged, so a run of a few scenarios (`-g`) keeps the rest.
  const merged = { ...known, ...sizes };
  const sorted = Object.fromEntries(
    Object.entries(merged).sort(([a], [b]) => a.localeCompare(b)),
  );
  fs.writeFileSync(file, JSON.stringify(sorted, null, 2) + "\n");
});

test.beforeAll(async () => {
  await seedDemoWorkspace();
});

test.beforeEach(async ({ context }) => {
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
  }, daemonToken());
  // The pictures show the desktop app, which is what the docs tell people to
  // install: macOS keys (⌘K) and the window's own title strip with the traffic
  // lights, which the system draws and a browser cannot. The app takes that
  // from the Tauri host, so a stand-in answers the one thing it asks.
  await context.addInitScript(
    ({ tok, base }: { tok: string; base: string }) => {
      Object.defineProperty(navigator, "platform", { get: () => "MacIntel" });
      // A window the size of the screen reads as full screen, which hides the
      // traffic lights and moves the controls; the docs show a normal window.
      Object.defineProperty(window.screen, "width", { get: () => 2560 });
      Object.defineProperty(window.screen, "height", { get: () => 1600 });
      (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {
        invoke: async (command: string) => {
          if (command === "get_daemon_info")
            return { baseUrl: base, token: tok };
          // The app and the daemon are one build.
          if (command === "daemon_version_matches") return true;
          return null;
        },
        transformCallback: () => 0,
        unregisterCallback: () => undefined,
        metadata: {
          currentWindow: { label: "main" },
          currentWebview: { label: "main", windowLabel: "main" },
        },
      };
    },
    { tok: daemonToken(), base: `http://127.0.0.1:${DOCS_DAEMON_PORT}/api/v1` },
  );
});

for (const lang of LANGS) {
  for (const theme of THEMES) {
    for (const shot of SHOTS) {
      test(`${shot.name} (${lang}, ${theme})`, async ({ page }) => {
        await page.addInitScript((l: string) => {
          try {
            localStorage.setItem("coffer.language", l);
            localStorage.removeItem("coffer.theme");
          } catch {
            /* storage blocked: the browser locale still decides */
          }
        }, lang);
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        await page.setViewportSize(shot.frame === "panel" ? PANEL : WINDOW);
        await page.goto(shot.route);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await shot.ready(page);
        await shot.prepare?.(page);
        await expect(page.locator(".animate-pulse")).toHaveCount(0);
        await expect(page.locator(".animate-spin")).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        // Let the page's own live refresh land before the picture is taken.
        await page.waitForTimeout(1500);

        const dir = path.join(OUT, lang, theme);
        fs.mkdirSync(dir, { recursive: true });
        let png: Buffer;
        if (shot.open) {
          const dialog = await shot.open(page);
          await page.waitForTimeout(500);
          png = await dialog.screenshot();
        } else if (shot.frame === "panel") {
          png = await page.screenshot({ clip: await panelBox(page) });
        } else {
          await addTrafficLights(page);
          png = await page.screenshot();
        }
        sizes[`${lang}/${theme}/${shot.name}`] = pngSize(png);
        fs.writeFileSync(
          path.join(dir, `${shot.name}.webp`),
          await toWebp(page, png),
        );
      });
    }
  }
}
