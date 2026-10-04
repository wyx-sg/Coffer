// e2e/web/specs/shell_agents.spec.ts
//
// The Agents page and the agent detail page against the real daemon: the two
// fixed rows, connecting an agent through the change preview, and the path tabs
// (six in the strip, two behind More; the model is a section of Overview).
//
// Detection looks for `claude` / `codex` on the daemon's PATH. start_daemon.sh
// puts `$HOME/bin` of the isolated HOME on it, so a machine without Codex (CI)
// gets a stand-in program there and the Codex row reads as installed. The
// isolated HOME has no `~/.codex`, so the row is "installed, never run" and
// Add creates the directory — inside the isolated HOME only.
import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { acceptance } from "./_acceptance";
import {
  beforeEachInjectToken,
  readDaemonToken,
  resolveResourceUid,
} from "./_helpers";

beforeEachInjectToken();

/** The isolated HOME start_daemon.sh chose (read when needed: it exists once the daemon is up). */
function home(): string {
  return fs
    .readFileSync(process.env.COFFER_E2E_HOME_FILE ?? "/tmp/coffer-e2e-home.path", "utf-8")
    .trim();
}

/** A stand-in `codex` on the daemon's PATH, used only where no real one is found first. */
function ensureCodexProgram(): void {
  const bin = path.join(home(), "bin");
  fs.mkdirSync(bin, { recursive: true });
  const program = path.join(bin, "codex");
  if (!fs.existsSync(program)) {
    fs.writeFileSync(program, '#!/bin/sh\necho "codex-cli 0.41.0"\n', {
      mode: 0o755,
    });
  }
}

async function api(
  method: string,
  route: string,
  body?: unknown,
): Promise<Response> {
  const { token, port } = readDaemonToken();
  return fetch(`http://127.0.0.1:${port}/api/v1${route}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** Take the codex agent out of Coffer entirely (entry, hook and registration). */
async function removeCodex(): Promise<void> {
  try {
    const uid = await resolveResourceUid("agent", "codex");
    if (uid === null) return;
    await api("DELETE", `/agents/${uid}/coffer-connection`);
    await api("DELETE", `/agents/${uid}`);
  } catch {
    // best-effort
  }
}

function row(page: Page, name: string) {
  return page.locator("tbody tr", { hasText: name }).first();
}

acceptance("agent-registry", "desktop app agents page", async ({ page }) => {
  // One registered agent (Codex, on a directory of its own) and one not added.
  ensureCodexProgram();
  await removeCodex();
  const configDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "coffer-e2e-agent-cfg-"),
  );
  try {
    expect(
      (await api("POST", "/agents", { type: "codex", config_dir: configDir }))
        .status,
    ).toBe(201);
    await page.goto("/agents");
    await expect(
      page.getByRole("heading", { name: /^agents$/i }),
    ).toBeVisible();

    // Exactly two rows, Claude Code then Codex — whatever is installed.
    const rows = page
      .locator("tbody tr")
      .filter({ hasText: /Claude Code|Codex/ });
    await expect(rows).toHaveCount(2, { timeout: 10_000 });
    await expect(rows.nth(0)).toContainText("Claude Code");
    await expect(rows.nth(1)).toContainText("Codex");

    // The registered row carries its directory and its Coffer state.
    const codex = row(page, "Codex");
    await expect(codex).toContainText(path.basename(configDir));
    await expect(codex).toContainText("Not connected");
    await expect(codex.getByRole("button", { name: "Connect" })).toBeVisible();

    // No Detect action and no Add agent dialog: detection is automatic.
    await expect(page.getByRole("button", { name: /detect/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /add agent/i })).toHaveCount(
      0,
    );

    // The row opens the agent's page, addressed by its type.
    await codex.getByText("Codex", { exact: true }).click();
    await expect(page).toHaveURL(/\/agents\/codex$/);
  } finally {
    await removeCodex();
    fs.rmSync(configDir, { recursive: true, force: true });
  }
});

acceptance(
  "agent-registry",
  "connecting an agent previews the change first",
  async ({ page }) => {
    ensureCodexProgram();
    await removeCodex();
    fs.rmSync(path.join(home(), ".codex"), { recursive: true, force: true });
    try {
      await page.goto("/agents");
      const codex = row(page, "Codex");
      await expect(codex.getByRole("button", { name: "Connect" })).toBeVisible({
        timeout: 15_000,
      });
      await codex.getByRole("button", { name: "Connect" }).click();

      // The preview names the file the add writes, and nothing is written yet.
      const dialog = page.getByRole("dialog");
      await expect(
        dialog.getByRole("heading", { name: "Review changes" }),
      ).toBeVisible();
      await expect(dialog).toContainText("config.toml");
      expect(await resolveResourceUid("agent", "codex")).toBeNull();

      await dialog
        .getByRole("button", { name: /^Apply \d+ changes?$/ })
        .click();
      await expect(dialog.getByRole("button", { name: "Done" })).toBeVisible({
        timeout: 20_000,
      });
      await dialog.getByRole("button", { name: "Done" }).click();

      // Registered under its default directory and connected.
      expect(await resolveResourceUid("agent", "codex")).not.toBeNull();
      await expect(row(page, "Codex")).toContainText("Connected", {
        timeout: 10_000,
      });
    } finally {
      await removeCodex();
    }
  },
);

acceptance(
  "agent-registry",
  "the agent detail page carries six tabs and a More menu",
  async ({ page }) => {
    ensureCodexProgram();
    await removeCodex();
    const configDir = fs.mkdtempSync(
      path.join(os.tmpdir(), "coffer-e2e-agent-cfg-"),
    );
    try {
      expect(
        (await api("POST", "/agents", { type: "codex", config_dir: configDir }))
          .status,
      ).toBe(201);
      await page.goto("/agents/codex/mcp-servers");

      // Six tabs in the strip, no counts, no Model tab (the model is a section
      // of Overview); Plugins and Memory sit behind More.
      const tabs = page.getByRole("tab");
      await expect(tabs).toHaveCount(6);
      expect(await tabs.allTextContents()).toEqual([
        "Overview",
        "Skills",
        "MCP servers",
        "Hooks",
        "Config files",
        "Sessions",
      ]);

      const paths: [RegExp, string][] = [
        [/^Skills/, "/skills"],
        [/^Hooks/, "/hooks"],
        [/^Config files/, "/config"],
        [/^Sessions/, "/sessions"],
        [/^Overview/, ""],
      ];
      for (const [name, suffix] of paths) {
        await page.getByRole("tab", { name }).click();
        await expect(page).toHaveURL(new RegExp(`/agents/codex${suffix}$`));
      }

      // More holds Plugins and Memory; picking one opens it at its own path.
      await page.getByRole("button", { name: /^More/ }).click();
      await page.getByRole("menuitem", { name: /^Plugins/ }).click();
      await expect(page).toHaveURL(/\/agents\/codex\/plugins$/);

      // Overview carries no Title or Name field.
      await expect(page.getByText(/^Title$/)).toHaveCount(0);
    } finally {
      await removeCodex();
      fs.rmSync(configDir, { recursive: true, force: true });
    }
  },
);
