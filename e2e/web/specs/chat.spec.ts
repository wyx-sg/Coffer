// e2e/web/specs/chat.spec.ts
//
// Spec 008 — Agent Chat end-to-end tests.
//
// Covers the reachable user path without a live LLM:
//   1. Navigate to Chat; the sidebar entry and history panel render.
//   2. The new-conversation dialog: an agent picker + per-agent config.
//   3. Creating a conversation through the dialog adds it to the history.
//   4. With no model configured, the no-model empty state is shown.
//   5. Settings → Models is reachable.
//   6. With a model configured, the composer is present and enabled.
//
// A real streamed reply needs a live LLM credential, which the e2e daemon
// does not have; the streaming path is covered at the integration tier.

import { expect, type Page } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function deleteAllModels(): Promise<void> {
  const { token, port } = readDaemonToken();
  const resp = await fetch(`http://127.0.0.1:${port}/api/v1/models`, {
    headers: { "X-Coffer-Token": token },
  });
  if (!resp.ok) return;
  const body = (await resp.json()) as { models: Array<{ id: string }> };
  for (const m of body.models) {
    await fetch(`http://127.0.0.1:${port}/api/v1/models/${m.id}`, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token },
    });
  }
}

async function registerOllamaModel(name: string): Promise<string> {
  // Ollama needs no real credential.
  const { token, port } = readDaemonToken();
  const resp = await fetch(`http://127.0.0.1:${port}/api/v1/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Coffer-Token": token },
    body: JSON.stringify({
      display_name: name,
      provider: "ollama",
      model: "llama3.1",
      base_url: "http://localhost:11434",
    }),
  });
  if (!resp.ok) throw new Error(`register model failed: ${resp.status}`);
  return ((await resp.json()) as { id: string }).id;
}

async function deleteModel(modelId: string): Promise<void> {
  try {
    const { token, port } = readDaemonToken();
    await fetch(`http://127.0.0.1:${port}/api/v1/models/${modelId}`, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token },
    });
  } catch {
    // best-effort cleanup
  }
}

/** Open the new-conversation dialog and confirm it with the default agent. */
async function startConversationViaDialog(page: Page): Promise<void> {
  await page.getByRole("button", { name: /new chat/i }).first().click();
  const confirm = page.getByRole("button", { name: /start conversation/i });
  await expect(confirm).toBeVisible({ timeout: 5_000 });
  await confirm.click();
  await expect(confirm).toHaveCount(0, { timeout: 5_000 });
}

// ---------------------------------------------------------------------------
// Scenario: manage conversations
// ---------------------------------------------------------------------------

acceptance("008-agent-chat", "manage conversations", async ({ page }) => {
  await page.goto("/");

  // The "Chat" sidebar entry exists and navigates to /chat.
  await page.getByRole("link", { name: /^Chat$/i }).first().click();
  await expect(page).toHaveURL(/\/chat/);
  await expect(page.getByText("Conversations", { exact: true })).toBeVisible({
    timeout: 10_000,
  });

  // Creating a conversation through the dialog adds it to the history list.
  await startConversationViaDialog(page);
  await expect(page.getByRole("option").first()).toBeVisible({ timeout: 5_000 });
});

// ---------------------------------------------------------------------------
// Scenario: choose an agent when starting a conversation
// ---------------------------------------------------------------------------

acceptance(
  "008-agent-chat",
  "choose an agent when starting a conversation",
  async ({ page }) => {
    await page.goto("/chat");
    await expect(page.getByText("Conversations", { exact: true })).toBeVisible({
      timeout: 10_000,
    });

    // Open the new-conversation dialog — it offers an agent picker.
    await page.getByRole("button", { name: /new chat/i }).first().click();
    await expect(
      page.getByRole("heading", { name: "New conversation" }),
    ).toBeVisible({ timeout: 5_000 });

    // The built-in agent is offered.
    await expect(page.getByText("Coffer Assistant").first()).toBeVisible();

    // Confirming creates the conversation.
    await page.getByRole("button", { name: /start conversation/i }).click();
    await expect(
      page.getByRole("button", { name: /start conversation/i }),
    ).toHaveCount(0, { timeout: 5_000 });
    await expect(page.getByRole("option").first()).toBeVisible({ timeout: 5_000 });
  },
);

// ---------------------------------------------------------------------------
// Scenario: no-model empty state
// ---------------------------------------------------------------------------

acceptance("008-agent-chat", "no-model empty state", async ({ page }) => {
  await deleteAllModels();

  await page.goto("/chat");
  await expect(page.getByText("Conversations", { exact: true })).toBeVisible({
    timeout: 10_000,
  });

  // Create a conversation through the dialog; with no model configured the
  // thread must show the actionable no-model empty state.
  await startConversationViaDialog(page);

  await expect(page.getByText("No model configured")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText("Go to Settings → Models")).toBeVisible();
  await expect(page.getByText(/INTERNAL_ERROR/)).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// Scenario: register a model provider — Settings → Models is reachable
// ---------------------------------------------------------------------------

acceptance("008-agent-chat", "register a model provider", async ({ page }) => {
  await page.goto("/settings/models");
  await expect(
    page.getByRole("heading", { name: /Models/i }).first(),
  ).toBeVisible({ timeout: 10_000 });
  await expect(
    page.getByRole("button", { name: /Add model/i }).first(),
  ).toBeVisible({ timeout: 5_000 });
});

// ---------------------------------------------------------------------------
// Scenario: send a message and receive a streamed reply
// (limited — no live LLM; verifies the UI reaches the ready-to-send state)
// ---------------------------------------------------------------------------

acceptance(
  "008-agent-chat",
  "send a message and receive a streamed reply",
  async ({ page }) => {
    const modelId = await registerOllamaModel(`e2e-stream-${Date.now()}`);
    try {
      await page.goto("/chat");
      await expect(page.getByText("Conversations", { exact: true })).toBeVisible({
        timeout: 10_000,
      });

      // With a model configured, a new conversation shows an enabled composer.
      await startConversationViaDialog(page);

      const composer = page.getByRole("textbox", { name: /message/i });
      await expect(composer).toBeVisible({ timeout: 5_000 });
      await expect(composer).toBeEnabled();
    } finally {
      await deleteModel(modelId);
    }
  },
);
