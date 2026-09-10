// e2e/web/specs/shell_knowledge.spec.ts
//
// The one /knowledge surface end-to-end. `memory` and `knowledge_base` used to
// be two resource kinds with two surfaces and two e2e specs; they are one kind
// now — a SCOPE holds both the entries an agent wrote and the documents someone
// ingested — so the walks live together here.
//
// Entries (spec knowledge §User Story 5): cold-start → /knowledge → write an entry
// into the global scope → list → clear the scope. Documents (spec knowledge): create
// a named collection through the UI dialog, ingest a document via the REST API
// (file-picker dialogs are not automatable portably), then drive SEARCH and the
// document list through the real UI.
//
// State is provisioned via the daemon's REST API so the tests stay robust
// against UI churn, but the page render is exercised against the real DOM. The
// global and per-project scopes auto-provision; only a named collection is
// created by hand.
//
// The acceptance markers keep their original spec ids and scenario strings: the
// merge renamed the surface, not the behaviour they pin.

import { expect, type Page } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

/** Open a scope's Documents tab (Entries is the default tab). */
async function openDocumentsTab(page: Page) {
  await page.getByRole("tab", { name: "Documents" }).click();
}

acceptance("knowledge", "clear a memory scope", async ({ page }) => {
  const { token, port } = readDaemonToken();
  const apiBase = `http://127.0.0.1:${port}/api/v1`;
  const headers = {
    "Content-Type": "application/json",
    "X-Coffer-Token": token,
    "X-Coffer-Actor": "e2e",
  };

  // 1. Cold-start the /knowledge page — heading must render. This also
  //    auto-provisions the global scope on the list call the page makes.
  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // 2. Write an entry into the global scope via the API (no LLM at write time).
  const addResp = await fetch(`${apiBase}/knowledge/global/entries`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text: "e2e entry about deploys", title: "e2e" }),
  });
  expect(addResp.status).toBe(201);

  // 3. List entries — at least the one we added is present.
  const listResp = await fetch(`${apiBase}/knowledge/global/entries?limit=50&offset=0`, {
    headers: { "X-Coffer-Token": token },
  });
  expect(listResp.status).toBe(200);
  const listed = (await listResp.json()) as { total: number };
  expect(listed.total).toBeGreaterThanOrEqual(1);

  // 4. Clear the entries lane (the scope Resource is preserved).
  const clearResp = await fetch(`${apiBase}/knowledge/global/entries`, {
    method: "DELETE",
    headers,
  });
  expect(clearResp.status).toBe(200);

  // 5. Entries are gone; the scope still exists.
  const afterResp = await fetch(`${apiBase}/knowledge/global/entries?limit=50&offset=0`, {
    headers: { "X-Coffer-Token": token },
  });
  const after = (await afterResp.json()) as { total: number };
  expect(after.total).toBe(0);

  const scopeResp = await fetch(`${apiBase}/knowledge/global`, {
    headers: { "X-Coffer-Token": token },
  });
  expect(scopeResp.status).toBe(200);
});

// Knowledge §User Story 5 — an entry is added (entries are agent-authored: the
// agent writes over the MCP gateway / API, the wire behind the UI & CLI). This
// pins that a written entry surfaces in the read-only UI and that the viewer
// hands the file off to an external editor (open/reveal, daemon-backed on the
// web) instead of editing in-app — humans correct entries in their own editor.
acceptance("knowledge", "user adds a fact", async ({ page }) => {
  const { token, port } = readDaemonToken();
  const entryText = `e2e ui entry ${Date.now().toString(36)}`;

  try {
    // The entry is authored programmatically (the agent's write).
    const add = await fetch(`http://127.0.0.1:${port}/api/v1/knowledge/global/entries`, {
      method: "POST",
      headers: {
        "X-Coffer-Token": token,
        "X-Coffer-Actor": "agent",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text: entryText, title: "e2e-entry" }),
    });
    expect(add.status).toBe(201);

    // Navigate /knowledge → the global scope's detail page via the table.
    await page.goto("/knowledge");
    await page.getByText("global", { exact: true }).first().click();

    // Entries is the default tab: the entry shows in the tree; select it and
    // confirm the body renders.
    await page.getByText("e2e-entry", { exact: true }).first().click();
    await expect(page.getByText(entryText).first()).toBeVisible();

    // The viewer is read-only — no in-app edit affordance — and offers the
    // open/reveal hand-off to an external editor (daemon-backed on the web).
    // Asserting visibility only (a click would shell out a real OS launcher).
    // `exact: true` — the default substring match would match "Open in editor".
    await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveCount(0);
    await expect(page.locator("textarea")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /open in editor/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /reveal/i })).toBeVisible();
  } finally {
    // Clear the lane even on failure so reruns against a reused daemon stay
    // isolated (safe under workers:1 — nothing else shares the scope mid-run).
    await fetch(`http://127.0.0.1:${port}/api/v1/knowledge/global/entries`, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e" },
    });
  }
});

acceptance("knowledge", "keyword search returns ranked passages", async ({ page }) => {
  const { token, port } = readDaemonToken();
  const apiBase = `http://127.0.0.1:${port}/api/v1`;
  const scopeName = `e2e-kb-${Date.now().toString(36)}`;

  try {
    // 1. /knowledge renders and the create dialog makes a NAMED collection
    //    end-to-end (the global / per-project scopes auto-provision instead).
    await page.goto("/knowledge");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "New collection" }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name", { exact: true }).fill(scopeName);
    // The dialog's submit button carries the same label as the page CTA.
    await dialog.getByRole("button", { name: "New collection" }).click();

    // The new collection appears in the table; click into its detail page.
    const row = page.getByText(scopeName, { exact: true }).first();
    await expect(row).toBeVisible();

    // 2. Ingest a markdown document via REST (no portable file-picker driving).
    const form = new FormData();
    form.append(
      "file",
      new File(["# Deploys\n\nwe deploy with make release\n"], "deploys.md", {
        type: "text/markdown",
      }),
    );
    const ingest = await fetch(`${apiBase}/knowledge/${scopeName}/documents`, {
      method: "POST",
      headers: { "X-Coffer-Token": token },
      body: form,
    });
    expect(ingest.status).toBe(201);

    // 3. Drive the Documents lane through the UI. The document row shows the
    //    markdown title ("Deploys"), not the source filename.
    await row.click();
    await openDocumentsTab(page);
    await expect(page.getByText("Deploys", { exact: true })).toBeVisible();
    await page.getByPlaceholder("Search this scope's documents…").fill("release");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByText(/make release/).first()).toBeVisible();
  } finally {
    // Clean up even on assertion failure so reruns against a reused daemon
    // stay isolated.
    await fetch(`${apiBase}/resources/knowledge/${scopeName}`, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token },
    });
  }
});
