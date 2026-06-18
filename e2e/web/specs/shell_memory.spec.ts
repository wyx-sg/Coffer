// e2e/web/specs/shell_memory.spec.ts
//
// Spec 007 §User Story 5 — the desktop /memory surface (redesign).
//
// Walk through cold-start → /memory → add a fact to the global store →
// list → clear the scope. State is provisioned via the daemon's REST API so
// the test stays robust against UI churn, but the page render is exercised
// against the real DOM. Memory stores are auto-provisioned per scope (global +
// per-project); there is no user-created/deleted named store anymore.
//
// The acceptance marker maps this walk to the spec scenario "clear a memory
// scope" — a P3 scenario already covered by backend tests; this e2e ensures the
// web UI wiring stays aligned.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

acceptance("007-memory", "clear a memory scope", async ({ page }) => {
  const { token, port } = readDaemonToken();
  const apiBase = `http://127.0.0.1:${port}/api/v1`;
  const headers = {
    "Content-Type": "application/json",
    "X-Coffer-Token": token,
    "X-Coffer-Actor": "e2e",
  };

  // 1. Cold-start the /memory page — heading must render. This also
  //    auto-provisions the global store on the list call the page makes.
  await page.goto("/memory");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // 2. Add a fact to the global store via the API (no LLM at write time).
  const addResp = await fetch(`${apiBase}/memory_stores/global/facts`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text: "e2e fact about deploys", name: "e2e" }),
  });
  expect(addResp.status).toBe(201);

  // 3. List facts — at least the one we added is present.
  const listResp = await fetch(
    `${apiBase}/memory_stores/global/facts?limit=50&offset=0`,
    { headers: { "X-Coffer-Token": token } },
  );
  expect(listResp.status).toBe(200);
  const listed = (await listResp.json()) as { total: number };
  expect(listed.total).toBeGreaterThanOrEqual(1);

  // 4. Clear the scope (the store Resource is preserved).
  const clearResp = await fetch(`${apiBase}/memory_stores/global/facts`, {
    method: "DELETE",
    headers,
  });
  expect(clearResp.status).toBe(200);

  // 5. Facts are gone; the store still exists.
  const afterResp = await fetch(
    `${apiBase}/memory_stores/global/facts?limit=50&offset=0`,
    { headers: { "X-Coffer-Token": token } },
  );
  const after = (await afterResp.json()) as { total: number };
  expect(after.total).toBe(0);

  const storeResp = await fetch(`${apiBase}/memory_stores/global`, {
    headers: { "X-Coffer-Token": token },
  });
  expect(storeResp.status).toBe(200);
});

// Spec 007 §User Story 5 — a fact is added (memory is AI-authored: the agent
// writes via the MCP `remember` tool / API, the wire behind the UI & CLI). This
// pins that an added fact surfaces in the read-only UI and that the viewer
// hands the file off to an external editor (Copy path on the web) instead of
// editing in-app — humans correct facts in their own editor.
acceptance("007-memory", "user adds a fact", async ({ page }) => {
  const { token, port } = readDaemonToken();
  const factText = `e2e ui fact ${Date.now().toString(36)}`;

  try {
    // The fact is authored programmatically (the agent's `remember`).
    const add = await fetch(`http://127.0.0.1:${port}/api/v1/memory_stores/global/facts`, {
      method: "POST",
      headers: {
        "X-Coffer-Token": token,
        "X-Coffer-Actor": "agent",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text: factText, name: "e2e-fact" }),
    });
    expect(add.status).toBe(201);

    // Navigate /memory → the global store's detail page via the stores table.
    await page.goto("/memory");
    await page.getByText("global", { exact: true }).first().click();

    // The fact shows in the tree; select it and confirm the body renders.
    await page.getByText("e2e-fact", { exact: true }).first().click();
    await expect(page.getByText(factText).first()).toBeVisible();

    // The viewer is read-only — no in-app edit affordance — and offers the
    // path hand-off to an external editor (Copy path on the web).
    await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);
    await expect(page.locator("textarea")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /copy path/i })).toBeVisible();
  } finally {
    // Clear the scope even on failure so reruns against a reused daemon stay
    // isolated (safe under workers:1 — nothing else shares the store mid-run).
    await fetch(`http://127.0.0.1:${port}/api/v1/memory_stores/global/facts`, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e" },
    });
  }
});
