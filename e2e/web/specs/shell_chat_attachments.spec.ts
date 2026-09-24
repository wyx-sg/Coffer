// e2e/web/specs/shell_chat_attachments.spec.ts
//
// Attach a file on the Chat page, send it, reload, and find it in the thread
// (spec chat "Attach files from the Chat page composer", "Show a message's
// attachments in the thread").
//
// The conversation is provisioned over REST. It names Codex because the e2e
// daemon's isolated HOME holds no Codex login, so the turn the send starts
// fails fast without reaching a model; the user message — text plus the
// attachment reference — is persisted before the turn runs either way, which
// is what the reload reads back.

import { expect, type Page } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

function api() {
  const { token, port } = readDaemonToken();
  return {
    base: `http://127.0.0.1:${port}/api/v1`,
    headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e" },
  };
}

async function createConversation(page: Page): Promise<string> {
  const { base, headers } = api();
  const res = await page.request.post(`${base}/chat/conversations`, {
    headers,
    data: { agent_key: "codex" },
  });
  expect(res.status()).toBe(201);
  return ((await res.json()) as { id: string }).id;
}

async function deleteConversation(page: Page, id: string): Promise<void> {
  const { base, headers } = api();
  await page.request.delete(`${base}/chat/conversations/${id}`, { headers });
}

acceptance(
  "chat",
  "attaching a file shows a chip and sends it with the message",
  async ({ page }) => {
    const id = await createConversation(page);
    try {
      await page.goto(`/chat/${id}`);
      const composer = page.getByTestId("composer");
      await expect(composer).toBeVisible();

      await page.getByTestId("composer-file-input").setInputFiles({
        name: "notes.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("the deploy window is Tuesday\n"),
      });
      const chips = composer.getByRole("list", { name: /attached files/i });
      await expect(chips).toContainText("notes.txt");

      const box = page.getByRole("textbox", { name: /message input/i });
      await box.fill("please read this");
      // Send is enabled once the upload finished; Enter sends like the button.
      await expect(page.getByRole("button", { name: /^send$/i })).toBeEnabled();
      await box.press("Enter");
      await expect(chips).toHaveCount(0);

      // The message went out with the upload: its persisted row carries the
      // reference by name and type, and no path.
      const { base, headers } = api();
      await expect
        .poll(async () => {
          const res = await page.request.get(`${base}/chat/conversations/${id}/messages`, {
            headers,
          });
          const body = (await res.json()) as {
            messages: { role: string; content: { type: string; filename?: string }[] }[];
          };
          const user = body.messages.find((m) => m.role === "user");
          return user?.content.filter((b) => b.type === "attachment").map((b) => b.filename);
        })
        .toEqual(["notes.txt"]);
    } finally {
      await deleteConversation(page, id);
    }
  },
);

acceptance("chat", "an attached file is shown in the thread after a reload", async ({ page }) => {
  const id = await createConversation(page);
  try {
    await page.goto(`/chat/${id}`);
    await page.getByTestId("composer-file-input").setInputFiles({
      name: "diagram.png",
      mimeType: "image/png",
      buffer: Buffer.from("89504e470d0a1a0a0000000d49484452", "hex"),
    });
    await expect(page.getByRole("button", { name: /^send$/i })).toBeEnabled();
    const box = page.getByRole("textbox", { name: /message input/i });
    await box.fill("what is this?");
    await box.press("Enter");

    // Wait until the row is persisted, then read the thread fresh.
    const { base, headers } = api();
    await expect
      .poll(async () => {
        const res = await page.request.get(`${base}/chat/conversations/${id}/messages`, {
          headers,
        });
        return ((await res.json()) as { messages: { role: string }[] }).messages.some(
          (m) => m.role === "user",
        );
      })
      .toBe(true);
    await page.reload();

    const chip = page.getByTestId("attachment-chip");
    await expect(chip).toHaveCount(1);
    await expect(chip).toContainText("diagram.png");
    await expect(chip).toContainText("image/png");
  } finally {
    await deleteConversation(page, id);
  }
});
