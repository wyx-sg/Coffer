// e2e/web/specs/chat.spec.ts
//
// Spec 008 — Agent Chat end-to-end tests.
//
// Covers the reachable user path without a live LLM:
//   1. Navigate to Chat; the sidebar entry and history panel render.
//   2. The draft surface: clicking "+" opens a blank draft whose top bar offers
//      the agent + model selectors (no modal dialog).
//   3. Sending the first message in the draft creates the conversation and adds
//      it to the history list.
//   4. With no model configured, the draft shows the no-model empty state.
//   5. Settings → Models is reachable.
//   6. With a model configured, the draft composer is present and enabled.
//
// A real streamed reply needs a live LLM credential, which the e2e daemon does
// not have; the streaming path is covered at the integration tier. Sending the
// first message still creates the conversation even when the turn then errors.

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

/** New flow: clicking "+" opens a blank draft; sending the first message is
 *  what creates the conversation. Requires a model so the composer renders. */
async function createConversationViaDraft(page: Page): Promise<void> {
  await page
    .getByRole("button", { name: /new chat/i })
    .first()
    .click();
  const composer = page.getByRole("textbox", { name: /message input/i });
  await expect(composer).toBeVisible({ timeout: 5_000 });
  await composer.fill("hello from e2e");
  await composer.press("Enter");
  // The conversation is created (and appears in the history) even though the
  // turn then errors without a live LLM.
  await expect(page.getByRole("option").first()).toBeVisible({
    timeout: 10_000,
  });
}

// ---------------------------------------------------------------------------
// Scenario: manage conversations
// ---------------------------------------------------------------------------

acceptance("008-agent-chat", "manage conversations", async ({ page }) => {
  const modelId = await registerOllamaModel(`e2e-manage-${Date.now()}`);
  try {
    await page.goto("/");

    // The "Vault Console" sidebar entry exists and navigates to /chat (ADR-021).
    await page
      .getByRole("link", { name: /^Vault Console$/i })
      .first()
      .click();
    await expect(page).toHaveURL(/\/chat/);
    await expect(page.getByRole("tab", { name: /^Active$/i })).toBeVisible({
      timeout: 10_000,
    });

    // Sending the first message in the draft adds a conversation to the history.
    await createConversationViaDraft(page);
  } finally {
    await deleteModel(modelId);
  }
});

// ---------------------------------------------------------------------------
// Scenario: choose an agent when starting a conversation
// ---------------------------------------------------------------------------

acceptance(
  "008-agent-chat",
  "choose an agent when starting a conversation",
  async ({ page }) => {
    await page.goto("/chat");
    await expect(page.getByRole("tab", { name: /^Active$/i })).toBeVisible({
      timeout: 10_000,
    });

    // The draft surface offers an agent picker in its top bar (no modal).
    // The built-in agent is offered and selected by default.
    await expect(page.getByText("Coffer Assistant").first()).toBeVisible({
      timeout: 5_000,
    });
  },
);

// ---------------------------------------------------------------------------
// Scenario: no-model empty state
// ---------------------------------------------------------------------------

acceptance("008-agent-chat", "no-model empty state", async ({ page }) => {
  await deleteAllModels();

  await page.goto("/chat");
  await expect(page.getByRole("tab", { name: /^Active$/i })).toBeVisible({
    timeout: 10_000,
  });

  // With no model configured, the draft surface shows the actionable no-model
  // empty state rather than a composer.
  await expect(page.getByText("No model configured")).toBeVisible({
    timeout: 5_000,
  });
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
// (limited — no live LLM; verifies the draft reaches the ready-to-send state)
// ---------------------------------------------------------------------------

acceptance(
  "008-agent-chat",
  "send a message and receive a streamed reply",
  async ({ page }) => {
    const modelId = await registerOllamaModel(`e2e-stream-${Date.now()}`);
    try {
      await page.goto("/chat");
      await expect(page.getByRole("tab", { name: /^Active$/i })).toBeVisible({
        timeout: 10_000,
      });

      // With a model configured, the draft shows an enabled composer.
      const composer = page.getByRole("textbox", { name: /message input/i });
      await expect(composer).toBeVisible({ timeout: 5_000 });
      await expect(composer).toBeEnabled();
    } finally {
      await deleteModel(modelId);
    }
  },
);
