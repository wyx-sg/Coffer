// e2e/web/specs/shell_agents.spec.ts
//
// Spec 004 §User Story 4 — the desktop /agents surface.
//
// TEST25-208: walk through cold-start → /agents → register → list → delete
// to prove the page is wired end-to-end against the real daemon (not a
// mocked fetch). We use the daemon's REST API to set up state before
// asserting in the UI, then exercise the UI's own Delete control to
// confirm the round-trip.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";
import * as os from "node:os";
import * as path from "node:path";
import * as fs from "node:fs";

beforeEachInjectToken();

function mkSkillDir(name: string): string {
  const dir = path.join(os.tmpdir(), `coffer-e2e-skills-${name}-${Date.now()}`);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

async function deleteAgentByApi(name: string): Promise<void> {
  try {
    const { token, port } = readDaemonToken();
    await fetch(`http://127.0.0.1:${port}/api/v1/agents/${name}`, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
    });
  } catch {
    // best-effort
  }
}

acceptance(
  "004-agent-registry",
  "desktop app agents page",
  async ({ page }) => {
    const { token, port } = readDaemonToken();
    const name = `e2e-cur-${Date.now().toString(36)}`;
    const skillDir = mkSkillDir(name);

    try {
      // 1. Cold-start the /agents page. With no agents registered up front
      //    (best-effort, since the daemon DB is shared across the suite),
      //    we navigate and assert the page renders without errors.
      await page.goto("/agents");
      await expect(
        page.getByRole("heading", { name: /^agents$/i }),
      ).toBeVisible();

      // 2. Register an agent via the daemon API (avoids brittleness against
      //    Radix Select shadow-DOM quirks under headless Chromium).
      const createResp = await fetch(`http://127.0.0.1:${port}/api/v1/agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Coffer-Token": token,
          "X-Coffer-Actor": "e2e",
        },
        body: JSON.stringify({
          type: "cursor",
          name,
          skill_dir: skillDir,
          description: "e2e",
        }),
      });
      expect(createResp.status).toBe(201);

      // 3. Reload + the page now lists the new agent.
      await page.reload();
      await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 });

      // 4. Delete via the UI — the table's Delete button calls
      //    window.confirm; auto-accept it.
      page.once("dialog", (d) => {
        void d.accept();
      });
      // The row exposes a Delete button — locate the one in the row that
      // contains our agent's name.
      const row = page.locator("tr", { hasText: name });
      await row.getByRole("button", { name: /delete/i }).click();

      // 5. The agent vanishes from the table.
      await expect(page.getByText(name)).toHaveCount(0, { timeout: 10_000 });
    } finally {
      await deleteAgentByApi(name);
      // Best-effort skill_dir cleanup.
      try {
        fs.rmSync(skillDir, { recursive: true, force: true });
      } catch {
        // ignore
      }
    }
  },
);
