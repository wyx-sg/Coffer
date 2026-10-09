// e2e/web/specs/shell_channels.spec.ts
//
// The Channels page against a live daemon: add a SeaTalk channel through the
// three-step Add dialog, see it in the list with a status, change two of its
// settings (they save as they change) and see them survive a reload, check
// the link to its conversations, and delete it.
//
// SeaTalk rather than Telegram on purpose: the e2e daemon has no SeaTalk SDK,
// so the adapter reports the SDK missing and nothing reaches the network. A
// Telegram channel would start polling api.telegram.org with the fake token.
//
// No acceptance marker: the channel scenarios are pinned by the component
// tests, which assert the page far more precisely. What this adds is that the
// dialog, the auto-save and delete agree with the real REST answers.

import { expect, test } from "@playwright/test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  beforeEachInjectToken,
  readDaemonToken,
  resolveResourceUid,
} from "./_helpers";

beforeEachInjectToken();

function api() {
  const { token, port } = readDaemonToken();
  return {
    base: `http://127.0.0.1:${port}/api/v1`,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
  };
}

/** A channel names the agent it drives, so the form needs one registered.
 *  Returns the uid of an agent this test created (to remove it after), or
 *  null when the daemon already had one. */
async function ensureAgent(): Promise<string | null> {
  const { base, headers } = api();
  const list = (await (await fetch(`${base}/agents`, { headers })).json()) as {
    items?: Array<{ uid: string }>;
  };
  if ((list.items ?? []).length > 0) return null;
  const configDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "coffer-e2e-channel-agent-"),
  );
  const resp = await fetch(`${base}/agents`, {
    method: "POST",
    headers,
    body: JSON.stringify({ type: "claude_code", config_dir: configDir }),
  });
  expect(resp.status).toBe(201);
  return ((await resp.json()) as { uid: string }).uid;
}

test("a SeaTalk channel is added, configured, reloaded and deleted from the Channels page", async ({
  page,
}) => {
  const { base, headers } = api();
  const name = `e2e-st-${Date.now().toString(36)}`;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "coffer-e2e-dir-"));
  const createdAgent = await ensureAgent();

  try {
    await page.goto("/channels");
    await expect(
      page.getByRole("heading", { name: "Channels", level: 1 }),
    ).toBeVisible();

    // 1 Platform → 2 Connect → 3 Pair.
    await page.getByRole("button", { name: "Add channel" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: /SeaTalk/ }).click();
    await dialog.getByRole("button", { name: "Next" }).click();
    await expect(
      dialog.getByRole("heading", { name: "Add a SeaTalk channel" }),
    ).toBeVisible();
    await dialog.getByLabel("Name").fill(name);
    await dialog.getByLabel("App ID").fill("e2e-app-1");
    await dialog
      .getByRole("textbox", { name: "App secret" })
      .fill("e2e-secret-not-real");
    await dialog.getByRole("button", { name: "Connect" }).click();

    await expect(
      dialog.getByRole("heading", { name: `Pair SeaTalk · ${name}` }),
    ).toBeVisible();
    await expect(dialog.getByTestId("channel-pairing-code")).toBeVisible();
    await dialog.getByRole("button", { name: "Pair later" }).click();
    await expect(dialog).toHaveCount(0);

    const uid = await resolveResourceUid("channel", name);
    expect(uid).not.toBeNull();
    await expect(page).toHaveURL(new RegExp(`/channels/${uid}$`));

    // The list shows it, with a status line once its status is read.
    const row = page
      .getByTestId("channel-row")
      .filter({ hasText: `SeaTalk · ${name}` });
    await expect(row).toBeVisible();
    await expect(row).not.toHaveAttribute("data-state", "loading");
    await expect(page.getByTestId("channel-state-word")).not.toHaveText("");

    // Overview links to the conversations this channel started.
    await expect(
      page.getByTestId("channel-conversations-link"),
    ).toHaveAttribute("href", `/conversations?source=${uid}`);

    // Settings save as they change. A directory is added outside the page (the
    // folder dialog is the host's), then made the default from its row.
    const current = (await (
      await fetch(`${base}/resources/${uid}`, { headers })
    ).json()) as { config: Record<string, unknown> };
    const seeded = await fetch(`${base}/resources/${uid}`, {
      method: "PATCH",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({
        config: { ...current.config, directories: [dir] },
      }),
    });
    expect(seeded.ok).toBe(true);
    await page.reload();
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page).toHaveURL(new RegExp(`/channels/${uid}/settings$`));
    await page.getByLabel("Start a new conversation after").fill("6");
    await page.getByLabel("Start a new conversation after").blur();
    await page
      .getByRole("button", { name: `Set ${dir} as the default` })
      .click();
    await expect
      .poll(async () => {
        const r = await fetch(`${base}/resources/${uid}`, { headers });
        const body = (await r.json()) as { config: Record<string, unknown> };
        const agentConfig = body.config.default_agent_config as
          Record<string, unknown> | null | undefined;
        return [body.config.new_conversation_after_idle_hours, agentConfig?.cwd];
      })
      .toEqual([6, dir]);

    await page.reload();
    await expect(page.getByLabel("Start a new conversation after")).toHaveValue("6");
    const directories = page.getByRole("list", { name: "Directories" });
    await expect(directories).toContainText(dir);
    await expect(
      page.getByRole("button", {
        name: `Stop starting new conversations in ${dir}`,
      }),
    ).toBeVisible();

    // Delete, from the danger zone.
    await page.getByRole("button", { name: "Delete…" }).click();
    const confirm = page.getByRole("dialog");
    await expect(confirm).toContainText("conversations stay in Conversations");
    await confirm.getByRole("button", { name: "Delete channel" }).click();
    await expect(
      page.getByTestId("channel-row").filter({ hasText: name }),
    ).toHaveCount(0);
    expect(await resolveResourceUid("channel", name)).toBeNull();
  } finally {
    const left = await resolveResourceUid("channel", name);
    if (left !== null) {
      await fetch(`${base}/resources/${left}`, {
        method: "DELETE",
        headers,
      }).catch(() => {});
    }
    if (createdAgent !== null) {
      await fetch(`${base}/agents/${createdAgent}`, {
        method: "DELETE",
        headers,
      }).catch(() => {});
    }
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
