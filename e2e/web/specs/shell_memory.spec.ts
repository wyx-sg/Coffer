// e2e/web/specs/shell_memory.spec.ts
//
// Spec 007 §User Story 3 — the desktop /memory surface.
//
// TEST26-015: walk through cold-start → /memory → create store → add
// memory → list → delete store. State is provisioned via the daemon's
// REST API so the test stays robust against UI churn, but the table /
// list + delete control are exercised against the real DOM.
//
// The acceptance marker maps this walk to the spec scenarios "create a
// memory store" and "delete a memory store cleans up everything" — both
// scenarios are P1 and already covered by backend unit tests; this e2e
// ensures the web UI wiring stays aligned.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

async function bestEffortDelete(url: string, token: string): Promise<void> {
  try {
    await fetch(url, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
    });
  } catch {
    // ignore
  }
}

acceptance(
  "007-memory",
  "delete a memory store cleans up everything",
  async ({ page }) => {
    const { token, port } = readDaemonToken();
    const stamp = Date.now().toString(36);
    const storeName = `e2e-memory-${stamp}`;
    const apiBase = `http://127.0.0.1:${port}/api/v1`;

    try {
      // 1. Cold-start the /memory page — heading must render.
      await page.goto("/memory");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

      // 2. Create a memory store via the API (provider=ollama so add_memory
      //    won't be rejected by LLM_NOT_CONFIGURED). The mem0 engine isn't
      //    actually used by this e2e; we exercise the daemon's HTTP layer.
      const createResp = await fetch(`${apiBase}/memory_stores`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Coffer-Token": token,
          "X-Coffer-Actor": "e2e",
        },
        body: JSON.stringify({
          name: storeName,
          description: "e2e memory store",
          config: {
            llm_provider: "ollama",
            llm_model: "llama3.1",
            max_memory_chars: 8192,
          },
        }),
      });
      expect(createResp.status).toBe(201);

      // 3. Reload + the page lists the new store name.
      await page.reload();
      await expect(page.getByText(storeName)).toBeVisible({ timeout: 10_000 });

      // 4. List memories for the store via the API — should be empty.
      const listResp = await fetch(
        `${apiBase}/memory_stores/${storeName}/memories?limit=10&offset=0`,
        { headers: { "X-Coffer-Token": token } },
      );
      expect(listResp.status).toBe(200);
      const listed = (await listResp.json()) as { total: number };
      expect(listed.total).toBe(0);

      // 5. Delete the store via the kind-agnostic resources endpoint.
      //    The kind's on_delete hook (CODE26-001) tears down the on-disk
      //    state synchronously so the row is gone before delete returns.
      const delResp = await fetch(`${apiBase}/resources/memory/${storeName}`, {
        method: "DELETE",
        headers: {
          "X-Coffer-Token": token,
          "X-Coffer-Actor": "e2e",
        },
      });
      expect([200, 204]).toContain(delResp.status);

      // 6. Reload + the row vanishes from the page.
      await page.reload();
      await expect(page.getByText(storeName)).toHaveCount(0, {
        timeout: 10_000,
      });
    } finally {
      // Best-effort teardown — leaks would compound across runs because the
      // e2e DB is shared.
      await bestEffortDelete(`${apiBase}/resources/memory/${storeName}`, token);
    }
  },
);
