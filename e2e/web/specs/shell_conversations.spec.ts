// e2e/web/specs/shell_conversations.spec.ts
//
// The Conversations page against the real daemon (spec chat "Show every agent's
// sessions on the Conversations page", "Rename and delete a conversation
// through its agent"): a list of sessions read through GET /agent-sessions — here
// the conversations IM channels opened, each row with its source badge, agent
// and working directory — the Source filter in the URL, and rename and delete
// from a row's ⋯ menu. The page has no conversation view and no reply box; New
// conversation is its header action.
//
// A channel conversation cannot be opened from a real chat here, so the spec
// makes the index rows an inbound message would have left: a SeaTalk channel
// bound to another machine (its adapter never starts on this one, so nothing
// reaches SeaTalk) and, written straight into the isolated HOME's database, the
// conversation rows and their thread bookkeeping. They carry no native session,
// so rename and delete act on the index alone, as the scenario "a conversation
// with no session is deleted from the index only" says. They are listed by
// naming their channel in `?source=`, which pages the conversation index.
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

import {
  beforeEachInjectToken,
  generateUniqueName,
  readDaemonToken,
} from "./_helpers";

beforeEachInjectToken();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYTHON = path.join(
  path.resolve(__dirname, "../../.."),
  ".venv/bin/python3",
);

function home(): string {
  const pointer =
    process.env.COFFER_E2E_HOME_FILE ?? "/tmp/coffer-e2e-home.path";
  return fs.readFileSync(pointer, "utf-8").trim();
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

async function createElsewhereChannel(name: string): Promise<string> {
  // Coffer mints the secret's id; the channel cites the ref it answers.
  const secret = await api("POST", "/secrets", {
    label: name,
    value: "e2e-not-a-secret",
  });
  if (!secret.ok)
    throw new Error(
      `secret write failed: ${secret.status} ${await secret.text()}`,
    );
  const ref = ((await secret.json()) as { ref: string }).ref;
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
  if (!res.ok)
    throw new Error(`channel create failed: ${res.status} ${await res.text()}`);
  return ((await res.json()) as { uid: string }).uid;
}

/** Write the index row of a channel's direct-chat conversation, as an inbound message would. */
function seedChannelConversation(
  id: string,
  title: string,
  channelUid: string,
  cwd: string,
): void {
  const script = `
import json, sqlite3, sys, datetime
db, conv, title, uid, cwd = sys.argv[1:6]
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
c = sqlite3.connect(db, timeout=10)
c.execute(
  "INSERT INTO conversations (id, agent_key, title, created_at, updated_at, agent_config, channel_uid, peer_chat_id)"
  " VALUES (?, 'codex', ?, ?, ?, ?, ?, ?)",
  (conv, title, now, now, json.dumps({"cwd": cwd}), uid, "e2e-chat"),
)
c.execute(
  "INSERT INTO channel_thread_history (resource_uid, chat_id, thread_id, conversation_id, chat_kind, opened_at)"
  " VALUES (?, ?, '', ?, 'direct', ?)",
  (uid, "e2e-chat", conv, now),
)
c.commit()
`;
  execFileSync(PYTHON, [
    "-c",
    script,
    path.join(home(), "runs.db"),
    id,
    title,
    channelUid,
    cwd,
  ]);
}

test.describe("Conversations page", () => {
  test("lists channel conversations with their source, agent and directory, filters by source, and has no thread", async ({
    page,
  }) => {
    const nameA = generateUniqueName("e2e-conv-a");
    const nameB = generateUniqueName("e2e-conv-b");
    const channelA = await createElsewhereChannel(nameA);
    const channelB = await createElsewhereChannel(nameB);
    const idA = generateUniqueName("conv-a");
    const idB = generateUniqueName("conv-b");
    const titleA = generateUniqueName("from seatalk a");
    const titleB = generateUniqueName("from seatalk b");
    seedChannelConversation(idA, titleA, channelA, "/work/alpha");
    seedChannelConversation(idB, titleB, channelB, "/work/beta");
    try {
      await page.goto(`/conversations?source=${channelA},${channelB}`);
      const list = page.getByRole("list", { name: "Conversations" });
      const rowOf = (title: string) =>
        list.getByRole("listitem").filter({ hasText: title });
      await expect(rowOf(titleA)).toContainText("SeaTalk · DM");
      await expect(rowOf(titleA)).toContainText("Codex");
      await expect(rowOf(titleA)).toContainText("/work/alpha");
      await expect(rowOf(titleB)).toBeVisible();

      // A header row names the columns; New conversation is the header's action;
      // no welcome page, no reply box, no detail page.
      await expect(list.locator("li[data-header]")).toContainText("Source");
      await expect(
        page.getByRole("button", { name: /new conversation/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("textbox", { name: /message input/i }),
      ).toHaveCount(0);
      const before = page.url();
      await rowOf(titleA).click();
      await expect(page).toHaveURL(before);
      // These rows carry no native session (no turn has run), so they show Not
      // started in place of Open in terminal; the row opens nothing and the page
      // stays a list.
      await expect(rowOf(titleA).getByText("Not started")).toBeVisible();
      await expect(
        rowOf(titleA).getByRole("button", { name: /^Open in / }),
      ).toHaveCount(0);

      // The Source pill narrows the list in the server and the address.
      await page.getByRole("button", { name: /^Source/ }).click();
      await page.getByRole("option", { name: `SeaTalk · ${nameB}` }).click();
      await page.keyboard.press("Escape");
      await expect(page).toHaveURL(new RegExp(`source=${channelA}$`));
      await expect(rowOf(titleB)).toHaveCount(0);
      await expect(rowOf(titleA)).toBeVisible();

      // A channel's own link narrows the list to it.
      await page.goto(`/conversations?source=${channelB}`);
      await expect(rowOf(titleB)).toBeVisible();
      await expect(rowOf(titleA)).toHaveCount(0);

      // The search matches the working directory too.
      await page.goto(`/conversations?source=${channelA},${channelB}`);
      await page
        .getByRole("textbox", { name: "Search titles and directories" })
        .fill("alpha");
      await expect(rowOf(titleB)).toHaveCount(0);
      await expect(rowOf(titleA)).toBeVisible();
    } finally {
      await api("DELETE", `/chat/conversations/${idA}`);
      await api("DELETE", `/chat/conversations/${idB}`);
      await api("DELETE", `/resources/${channelA}`);
      await api("DELETE", `/resources/${channelB}`);
    }
  });

  test("a row renames in place and deletes after asking", async ({ page }) => {
    const channel = await createElsewhereChannel(
      generateUniqueName("e2e-conv-menu"),
    );
    const id = generateUniqueName("conv-menu");
    const title = generateUniqueName("to rename");
    seedChannelConversation(id, title, channel, "/work/menu");
    try {
      await page.goto(`/conversations?source=${channel}`);
      const list = page.getByRole("list", { name: "Conversations" });
      const row = list.getByRole("listitem").filter({ hasText: title });
      await row.hover();
      await row
        .getByRole("button", { name: `More actions for ${title}` })
        .click();
      await expect(page.getByRole("menuitem")).toHaveText([
        "Rename",
        "Delete…",
      ]);
      await page.getByRole("menuitem", { name: "Rename" }).click();
      const renamed = `${title} renamed`;
      const input = list.getByRole("textbox", { name: "Title" });
      await input.fill(renamed);
      await input.press("Enter");
      const renamedRow = list
        .getByRole("listitem")
        .filter({ hasText: renamed });
      await expect(renamedRow).toBeVisible();

      await renamedRow.hover();
      await renamedRow
        .getByRole("button", { name: `More actions for ${renamed}` })
        .click();
      await page.getByRole("menuitem", { name: "Delete…" }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toContainText(`Delete “${renamed}”?`);
      await expect(dialog).toContainText("cannot be recovered");
      await dialog.getByRole("button", { name: "Delete conversation" }).click();
      await expect(renamedRow).toHaveCount(0);
    } finally {
      await api("DELETE", `/chat/conversations/${id}`);
      await api("DELETE", `/resources/${channel}`);
    }
  });
});
