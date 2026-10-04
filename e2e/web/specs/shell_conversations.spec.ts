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
// a model; a stand-in `codex` on the daemon's PATH plus a registered codex agent
// make the agent a managed one, which chat offers and runs (spec chat "Offer and
// run only managed agents").
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

import {
  beforeEachInjectToken,
  generateUniqueName,
  readDaemonToken,
  registerManagedCodex,
} from "./_helpers";

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
  execFileSync(PYTHON, ["-c", script, path.join(home(), "runs.db"), conversationId, channelUid]);
}

test.describe("Conversations page", () => {
  test("lists every conversation with its source, filters by source, opens one beside the list", async ({
    page,
  }) => {
    const channelName = generateUniqueName("e2e-conv-ch");
    const channel = await createElsewhereChannel(channelName);
    const webTitle = generateUniqueName("from the web");
    const web = await createConversation(webTitle);
    const viaChannel = await createConversation(generateUniqueName("from seatalk"));
    bindToChannel(viaChannel, channel);
    try {
      await page.goto("/conversations");
      // A list of rows (no table): each row is the list item holding its link
      // (which carries the active filter in its query).
      const list = page.getByRole("list", { name: "Conversations" });
      const rowOf = (id: string) =>
        list.getByRole("listitem").filter({ has: page.locator(`a[href^="/conversations/${id}"]`) });
      const webRow = rowOf(web);
      const channelRow = rowOf(viaChannel);
      await expect(webRow).toContainText("Coffer");
      await expect(channelRow).toContainText("SeaTalk · DM");
      // No welcome page and no composer: the page opens on the list.
      await expect(page.getByRole("textbox", { name: /message input/i })).toHaveCount(0);

      // The Source pill lists Coffer and each channel, several at once.
      await page.getByRole("button", { name: /^Source/ }).click();
      await page.getByRole("option", { name: `SeaTalk · ${channelName}` }).click();
      await page.keyboard.press("Escape");
      await expect(page).toHaveURL(new RegExp(`source=${channel}`));
      await expect(webRow).toHaveCount(0);
      await expect(channelRow).toBeVisible();

      // A channel's own link narrows the list to it; the earlier ?channel= form
      // is read once as that source and the address rewritten.
      await page.goto(`/conversations?channel=${channel}`);
      await expect(page).toHaveURL(new RegExp(`source=${channel}`));
      await expect(channelRow).toBeVisible();
      await expect(webRow).toHaveCount(0);

      await page.goto("/conversations");
      await webRow.getByRole("link").click();
      await expect(page).toHaveURL(new RegExp(`/conversations/${web}$`));
      await expect(page.getByRole("heading", { level: 1, name: webTitle })).toBeVisible();
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
    const codex = await registerManagedCodex();
    const channel = await createElsewhereChannel(generateUniqueName("e2e-mirror-ch"));
    const id = await createConversation(generateUniqueName("mirrored"));
    bindToChannel(id, channel);
    try {
      await page.goto(`/conversations/${id}`);
      // The title bar names where a reply also goes; the reply box says nothing.
      await expect(page.getByText("SeaTalk · DM", { exact: true })).toBeVisible();

      // The channel's adapter runs on another machine, so the reply waits.
      const box = page.getByRole("textbox", { name: /message input/i });
      await box.fill("checking from Coffer");
      await box.press("Enter");
      await expect(page.getByText("Not delivered to SeaTalk yet")).toBeVisible();
    } finally {
      await api("DELETE", `/chat/conversations/${id}`);
      await api("DELETE", `/resources/${channel}`);
      await codex.dispose();
    }
  });

  test("New conversation opens the draft; the first send creates the conversation", async ({
    page,
  }) => {
    const codex = await registerManagedCodex();
    let created: string | null = null;
    try {
      await page.goto("/conversations");
      await page.getByRole("button", { name: /new conversation/i }).first().click();
      // No dialog: straight to the draft, where agent and workspace are chosen.
      await expect(page).toHaveURL(/\/conversations\/new$/);
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Workspace" })).toBeVisible();
      // Codex: with no login in the isolated HOME its turn fails fast, locally.
      await page.getByRole("combobox", { name: "Agent", exact: true }).click();
      await page.getByRole("option", { name: /codex/i }).click();
      const box = page.getByRole("textbox", { name: /message input/i });
      await box.fill("hello from the draft");
      await box.press("Enter");
      await expect(page).not.toHaveURL(/\/conversations\/new$/);
      created = new URL(page.url()).pathname.split("/").pop() ?? null;
      await expect(page.getByText("hello from the draft")).toBeVisible();
    } finally {
      if (created) await api("DELETE", `/chat/conversations/${created}`);
      await codex.dispose();
    }
  });
});
