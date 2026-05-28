// e2e/web/specs/shell_skills.spec.ts
//
// Spec 005 §User Story 6 — the desktop /skills surface.
//
// TEST21-014: walk through cold-start → /skills → import a local skill →
// enable for an agent → disable → remove. State is provisioned via the
// daemon's REST API (not by clicking through forms) so the test stays
// robust against UI churn, but the table + delete control are exercised
// against the real DOM.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

beforeEachInjectToken();

function mkSkillFolder(name: string): string {
  const dir = path.join(os.tmpdir(), `coffer-e2e-skill-${name}-${Date.now()}`);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, "SKILL.md"),
    `---\nname: ${name}\ndescription: e2e test skill ${name}.\n---\n\nbody\n`,
    "utf-8",
  );
  return dir;
}

function mkAgentSkillDir(suffix: string): string {
  const dir = path.join(
    os.tmpdir(),
    `coffer-e2e-agent-skills-${suffix}-${Date.now()}`,
  );
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

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
  "005-skill-manager",
  "desktop and CLI cover every operation",
  async ({ page }) => {
    const { token, port } = readDaemonToken();
    const stamp = Date.now().toString(36);
    const skillName = `e2e-skill-${stamp}`;
    const agentName = `e2e-cur-${stamp}`;
    const skillSrc = mkSkillFolder(skillName);
    const agentSkillDir = mkAgentSkillDir(stamp);

    try {
      // 1. Cold-start the /skills page — heading must render.
      await page.goto("/skills");
      await expect(
        page.getByRole("heading", { name: /^skills$/i }),
      ).toBeVisible();

      // 2. Register an agent so the imported skill has somewhere to bind to.
      const agentResp = await fetch(`http://127.0.0.1:${port}/api/v1/agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Coffer-Token": token,
          "X-Coffer-Actor": "e2e",
        },
        body: JSON.stringify({
          type: "cursor",
          name: agentName,
          skill_dir: agentSkillDir,
          description: "e2e",
        }),
      });
      expect(agentResp.status).toBe(201);

      // 3. Import the skill via the API (auto-binds against the new agent).
      const importResp = await fetch(
        `http://127.0.0.1:${port}/api/v1/skills/import`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Coffer-Token": token,
            "X-Coffer-Actor": "e2e",
          },
          body: JSON.stringify({ path: skillSrc }),
        },
      );
      expect(importResp.status).toBe(201);
      const imported = (await importResp.json()) as {
        bindings: Array<{ agent_name: string; enabled: boolean }>;
      };
      expect(
        imported.bindings.some((b) => b.agent_name === agentName && b.enabled),
      ).toBe(true);
      // The agent-side symlink exists on disk after a successful enable.
      expect(fs.existsSync(path.join(agentSkillDir, skillName))).toBe(true);

      // 4. Reload + the page lists the skill name + binding cell.
      await page.reload();
      await expect(page.getByText(skillName)).toBeVisible({ timeout: 10_000 });

      // 5. Disable the binding via the API; the symlink disappears.
      const disableResp = await fetch(
        `http://127.0.0.1:${port}/api/v1/skills/${skillName}/disable`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Coffer-Token": token,
            "X-Coffer-Actor": "e2e",
          },
          body: JSON.stringify({ agent_name: agentName }),
        },
      );
      expect(disableResp.status).toBe(200);
      expect(fs.existsSync(path.join(agentSkillDir, skillName))).toBe(false);

      // 6. Remove the skill through the UI's Delete button — the table row
      //    has its own button and window.confirm is auto-accepted.
      page.once("dialog", (d) => {
        void d.accept();
      });
      const row = page.locator("tr", { hasText: skillName });
      await row.getByRole("button", { name: /delete/i }).click();

      // 7. The row vanishes from the table.
      await expect(page.getByText(skillName)).toHaveCount(0, {
        timeout: 10_000,
      });
    } finally {
      // Best-effort teardown — leaks would compound across runs because the
      // e2e DB is shared.
      await bestEffortDelete(
        `http://127.0.0.1:${port}/api/v1/skills/${skillName}`,
        token,
      );
      await bestEffortDelete(
        `http://127.0.0.1:${port}/api/v1/agents/${agentName}`,
        token,
      );
      try {
        fs.rmSync(skillSrc, { recursive: true, force: true });
        fs.rmSync(agentSkillDir, { recursive: true, force: true });
      } catch {
        // ignore
      }
    }
  },
);
