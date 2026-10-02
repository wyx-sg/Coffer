// e2e/web/specs/shell_conversations.spec.ts
//
// The Conversations page against the real daemon (spec chat "Show every
// conversation on the Conversations page", "Show where a reply will also be
// sent"): the list with each row's source badge and the source filter, a
// conversation opened beside the list, New conversation opening the
// draft, and a channel conversation's reply box saying where a reply also goes
// and marking a reply the channel has not received yet.
//
// A channel conversation cannot be opened from a real chat here, so the spec
// makes one: a SeaTalk channel bound to another machine (its adapter never
// starts on this one, so nothing reaches SeaTalk), a web conversation, and —
// written straight into the isolated HOME's database — the binding and the
// thread row an inbound message would have left. Conversations name Codex:
// the isolated HOME holds no Codex login, so a turn fails fast without reaching
// a model; a stand-in `codex` on the daemon's PATH makes the agent available.
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

import { beforeEachInjectToken, generateUniqueName, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYTHON = path.join(path.resolve(__dirname, "../../.."), ".venv/bin/python3");

function home(): string {
  const pointer = process.env.COFFER_E2E_HOME_FILE ?? "/tmp/coffer-e2e-home.path";
  return fs.readFileSync(pointer, "utf-8").trim();
}

async function api(method: string, route: string, body?: unknown): Promise<Response> {
  const { token, port } = readDaemonToken();
  return fetch(`http://127.0.0.1:${port}/api/v1${route}`, {
    method,
    headers: { "Content-Type": "application/json", "X-Coffer-Token": token, "X-Coffer-Actor": "e2e" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function ensureCodexProgram(): void {
  const bin = path.join(home(), "bin");
  fs.mkdirSync(bin, { recursive: true });
  const program = path.join(bin, "codex");
  if (!fs.existsSync(program)) {
    fs.writeFileSync(program, '#!/bin/sh\necho "codex-cli 0.41.0"\n', { mode: 0o755 });
  }
}

async function createConversation(title: string): Promise<string> {
  const res = await api("POST", "/chat/conversations", { agent_key: "codex" });
  expect(res.status).toBe(201);
  const id = ((await res.json()) as { id: string }).id;
  await api("PATCH", `/chat/conversations/${id}`, { title });
  return id;
}

async function createElsewhereChannel(name: string): Promise<string> {
  const ref = `channel/${name}/app-secret`;
  const secret = await api("POST", "/secrets", { ref, value: "e2e-not-a-secret" });
  if (!secret.ok) throw new Error(`secret write failed: ${secret.status} ${await secret.text()}`);
  const res = await api("POST", "/resources", {
    kind: "channel",
    name,
    config: {
      channel_type: "seatalk",
      app_id: "e2e-app",
      app_secret_ref: ref,
      runs_on: "e2e-another-machine",
    },
  });
  if (!res.ok) throw new Error(`channel create failed: ${res.status} ${await res.text()}`);
  return ((await res.json()) as { uid: string }).uid;
}

/** Bind a web conversation to a channel's direct chat, as an inbound message would. */
function bindToChannel(conversationId: string, channelUid: string): void {
  const script = `
import sqlite3, sys, datetime
db, conv, uid = sys.argv[1:4]
c = sqlite3.connect(db, timeout=10)
c.execute("UPDATE conversations SET channel_uid = ?, peer_chat_id = ? WHERE id = ?", (uid, "e2e-chat", conv))
c.execute(
  "INSERT INTO channel_thread_history (resource_uid, chat_id, thread_id, conversation_id, chat_kind, opened_at)"
  " VALUES (?, ?, '', ?, 'direct', ?)",
  (uid, "e2e-chat", conv, datetime.datetime.now(datetime.timezone.utc).isoformat()),
)
c.commit()
`;
  execFileSync(PYTHON, ["-c", script, path.join(home(), "coffer.db"), conversationId, channelUid]);
}

test.describe("Conversations page", () => {
  test("lists every conversation with its source, filters by source, opens one beside the list", async ({
    page,
  }) => {
    const channel = await createElsewhereChannel(generateUniqueName("e2e-conv-ch"));
    const web = await createConversation(generateUniqueName("from the web"));
    const viaChannel = await createConversation(generateUniqueName("from seatalk"));
    bindToChannel(viaChannel, channel);
    try {
      await page.goto("/conversations");
      const table = page.getByRole("table", { name: "Conversations" });
      const webRow = table.locator(`tr[data-conversation="${web}"]`);
      const channelRow = table.locator(`tr[data-conversation="${viaChannel}"]`);
      await expect(webRow).toContainText("Coffer");
      await expect(channelRow).toContainText("SeaTalk · DM");
      // No welcome page and no composer: the page opens on the list.
      await expect(page.getByRole("textbox", { name: /message input/i })).toHaveCount(0);

      await page.getByRole("group", { name: "Source" }).getByRole("button", { name: "SeaTalk" }).click();
      await expect(page).toHaveURL(/source=seatalk/);
      await expect(webRow).toHaveCount(0);
      await expect(channelRow).toBeVisible();

      // A channel's own link narrows the list to it.
      await page.goto(`/conversations?channel=${channel}`);
      await expect(channelRow).toBeVisible();
      await expect(webRow).toHaveCount(0);

      await page.goto("/conversations");
      await webRow.getByRole("link").click();
      await expect(page).toHaveURL(new RegExp(`/conversations/${web}$`));
      await expect(page.getByRole("list", { name: /conversation history/i })).toBeVisible();
      await expect(page.getByRole("textbox", { name: /message input/i })).toBeVisible();
    } finally {
      await api("DELETE", `/chat/conversations/${web}`);
      await api("DELETE", `/chat/conversations/${viaChannel}`);
      await api("DELETE", `/resources/${channel}`);
    }
  });

  test("a channel conversation says where a reply also goes, and marks one not delivered yet", async ({
    page,
  }) => {
    const channel = await createElsewhereChannel(generateUniqueName("e2e-mirror-ch"));
    const id = await createConversation(generateUniqueName("mirrored"));
    bindToChannel(id, channel);
    try {
      await page.goto(`/conversations/${id}`);
      await expect(page.getByText("Also sends to SeaTalk · direct chat")).toBeVisible();

      // The channel's adapter runs on another machine, so the reply waits.
      const box = page.getByRole("textbox", { name: /message input/i });
      await box.fill("checking from Coffer");
      await box.press("Enter");
      await expect(page.getByText("Not delivered to SeaTalk yet")).toBeVisible();
    } finally {
      await api("DELETE", `/chat/conversations/${id}`);
      await api("DELETE", `/resources/${channel}`);
    }
  });

  test("New conversation opens the draft; the first send creates the conversation", async ({
    page,
  }) => {
    ensureCodexProgram();
    let created: string | null = null;
    try {
      await page.goto("/conversations");
      await page.getByRole("button", { name: /new conversation/i }).first().click();
      // No dialog: straight to the draft, where agent and workspace are chosen.
      await expect(page).toHaveURL(/\/conversations\/new$/);
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Workspace" })).toBeVisible();
      // Codex: with no login in the isolated HOME its turn fails fast, locally.
      await page.getByRole("combobox", { name: "Agent" }).click();
      await page.getByRole("option", { name: /codex/i }).click();
      const box = page.getByRole("textbox", { name: /message input/i });
      await box.fill("hello from the draft");
      await box.press("Enter");
      await expect(page).not.toHaveURL(/\/conversations\/new$/);
      created = new URL(page.url()).pathname.split("/").pop() ?? null;
      await expect(page.getByText("hello from the draft")).toBeVisible();
    } finally {
      if (created) await api("DELETE", `/chat/conversations/${created}`);
    }
  });
});
