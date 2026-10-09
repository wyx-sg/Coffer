// e2e/docs/specs/shots.docs.spec.ts
//
// One scenario per docs image: open the page on the seeded daemon and write a
// PNG for each language and theme into docs-site/public/shots/. The list below
// is the whole set; a page is added here only when a reader needs to find
// something on screen.
import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import { DOCS_HOME } from "../env";
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
}

const heading = (re: RegExp) => async (page: Page) => {
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await expect(page.locator("main#main")).toContainText(re);
};

export const SHOTS: Shot[] = [
  { name: "overview", route: "/", ready: heading(/sentry/) },
  {
    name: "agents",
    route: "/agents/claude_code",
    ready: heading(/Claude Code/),
  },
  {
    name: "mcp-servers",
    route: "/mcp-servers/github",
    // The server's own tools are listed once the daemon has connected to it.
    ready: async (page) => {
      await page.getByRole("button", { name: /^(Test|测试)$/ }).click();
      await expect(page.locator("main#main")).toContainText(
        "Open an issue in a repository.",
        { timeout: 20_000 },
      );
    },
  },
  {
    name: "skills",
    route: "/skills/gh-triage",
    ready: async (page) => {
      await expect(
        page.getByRole("heading", { level: 2, name: "gh-triage" }).first(),
      ).toBeVisible();
      await expect(page.locator("main#main")).toContainText(
        "Sort new GitHub issues by area and urgency.",
      );
    },
  },
  { name: "knowledge", route: "/knowledge", ready: heading(/engineering/) },
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
        await page.goto(shot.route);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await shot.ready(page);
        await expect(page.locator(".animate-pulse")).toHaveCount(0);
        await expect(page.locator(".animate-spin")).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        // Let the page's own live refresh land before the picture is taken.
        await page.waitForTimeout(1500);

        const dir = path.join(OUT, lang, theme);
        fs.mkdirSync(dir, { recursive: true });
        const png = await page.screenshot();
        fs.writeFileSync(
          path.join(dir, `${shot.name}.webp`),
          await toWebp(page, png),
        );
      });
    }
  }
}
