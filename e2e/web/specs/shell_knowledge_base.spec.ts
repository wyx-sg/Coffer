// e2e/web/specs/shell_knowledge_base.spec.ts
//
// Spec 006 — the desktop /knowledge surface end-to-end.
//
// Create a KB through the UI dialog, ingest a document via the REST API
// (file-picker dialogs are not automatable portably), then drive SEARCH and
// the document list through the real UI. This is the browser-level companion
// to the backend acceptance suite: it pins frontend↔backend wiring for the
// keyword search path.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

acceptance(
  "006-knowledge-base",
  "keyword search returns ranked passages",
  async ({ page }) => {
    const { token, port } = readDaemonToken();
    const apiBase = `http://127.0.0.1:${port}/api/v1`;
    const kbName = `e2e-kb-${Date.now().toString(36)}`;

    try {
    // 1. /knowledge-bases renders and the create dialog works end-to-end.
    await page.goto("/knowledge-bases");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "New knowledge base" }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name", { exact: true }).fill(kbName);
    // The dialog's submit button carries the same label as the page CTA.
    await dialog.getByRole("button", { name: "New knowledge base" }).click();

    // The new KB appears in the table; click into its detail page.
    const row = page.getByText(kbName, { exact: true }).first();
    await expect(row).toBeVisible();

    // 2. Ingest a markdown document via REST (no portable file-picker driving).
    const form = new FormData();
    form.append(
      "file",
      new File(["# Deploys\n\nwe deploy with make release\n"], "deploys.md", {
        type: "text/markdown",
      }),
    );
    const ingest = await fetch(`${apiBase}/knowledge_bases/${kbName}/documents`, {
      method: "POST",
      headers: { "X-Coffer-Token": token },
      body: form,
    });
    expect(ingest.status).toBe(201);

    // 3. Drive the search panel through the UI. The document row shows the
    //    markdown title ("Deploys"), not the source filename.
    await row.click();
    await expect(page.getByText("Deploys", { exact: true })).toBeVisible();
    await page.getByPlaceholder("Search this knowledge base…").fill("release");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByText(/make release/).first()).toBeVisible();

    } finally {
      // Clean up even on assertion failure so reruns against a reused daemon
      // stay isolated.
      await fetch(`${apiBase}/resources/knowledge_base/${kbName}`, {
        method: "DELETE",
        headers: { "X-Coffer-Token": token },
      });
    }
  },
);
