// e2e/web/specs/shell_skills.spec.ts
//
// The skill-manager spec §User Story 6 — the desktop /skills surface.
//
// TEST21-014: walk through cold-start → /skills → import a local skill (which
// delivers it to the in-scope agent) → disable the skill (which reclaims the
// delivered copy) → remove. State is provisioned via the daemon's REST API
// (not by clicking through forms) so the test stays robust against UI churn,
// but the library, the open skill's tabs and its Delete are exercised against
// the real DOM.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import {
  beforeEachInjectToken,
  readDaemonToken,
  resolveResourceUid,
} from "./_helpers";
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

// The agent's config dir. Skills are delivered to <config_dir>/skills/, which
// registration auto-creates — so this only needs to exist as a directory.
function mkAgentConfigDir(suffix: string): string {
  const dir = path.join(
    os.tmpdir(),
    `coffer-e2e-agent-cfg-${suffix}-${Date.now()}`,
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
  "skill-manager",
  "desktop and CLI cover every operation",
  async ({ page }) => {
    const { token, port } = readDaemonToken();
    const stamp = Date.now().toString(36);
    const skillName = `e2e-skill-${stamp}`;
    // An agent is one per type and named by it.
    const agentName = "claude-code";
    const skillSrc = mkSkillFolder(skillName);
    const agentConfigDir = mkAgentConfigDir(stamp);
    // Skills are delivered under <config_dir>/skills/<name>.
    const deliveredSkill = path.join(agentConfigDir, "skills", skillName);

    try {
      // 1. Cold-start the /skills page — heading must render.
      await page.goto("/skills");
      await expect(
        page.getByRole("heading", { name: /^skills$/i }),
      ).toBeVisible();

      // 2. Register an agent so the imported skill has somewhere to bind to,
      //    clearing any claude-code agent the shared e2e DB already holds.
      const existingAgent = await resolveResourceUid("agent", agentName);
      if (existingAgent !== null)
        await bestEffortDelete(
          `http://127.0.0.1:${port}/api/v1/agents/${existingAgent}`,
          token,
        );
      const agentResp = await fetch(`http://127.0.0.1:${port}/api/v1/agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Coffer-Token": token,
          "X-Coffer-Actor": "e2e",
        },
        body: JSON.stringify({
          type: "claude_code",
          config_dir: agentConfigDir,
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
        bindings: Array<{ agent_name: string }>;
      };
      // A binding row IS a live delivery — the wire reports no other kind.
      expect(imported.bindings.some((b) => b.agent_name === agentName)).toBe(
        true,
      );
      // The agent-side symlink exists on disk after a successful delivery.
      expect(fs.existsSync(deliveredSkill)).toBe(true);

      // 4. Reload: the library lists the skill, and opening its row shows
      //    the skill beside the list, on its Files tab with SKILL.md open.
      await page.reload();
      const library = page.getByRole("list", { name: "Library" });
      const row = library.getByRole("link", { name: new RegExp(skillName) });
      await expect(row).toBeVisible({ timeout: 10_000 });
      await row.click();
      await expect(page).toHaveURL(new RegExp(`/skills/${skillName}$`));
      await expect(
        page.getByRole("heading", { level: 2, name: skillName }),
      ).toBeVisible();
      await expect(
        page.getByRole("tab", { name: "Files", selected: true }),
      ).toBeVisible();

      // 4b. The Delivery tab shows the agent's copy as linked.
      await page.getByRole("tab", { name: "Delivery" }).click();
      await expect(page).toHaveURL(
        new RegExp(`/skills/${skillName}/delivery$`),
      );
      await expect(
        page.getByTestId(`skill-delivery-${agentName}`),
      ).toContainText("Linked");

      // 5. Disable the SKILL via the API — delivery is decided on the skill
      //    (enabled + scope), so disabling it reclaims every copy and the
      //    symlink disappears.
      const skillUid = await resolveResourceUid("skill", skillName);
      if (skillUid === null) throw new Error(`no skill named ${skillName}`);
      const disableResp = await fetch(
        `http://127.0.0.1:${port}/api/v1/resources/${skillUid}/disable`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Coffer-Token": token,
            "X-Coffer-Actor": "e2e",
          },
        },
      );
      expect(disableResp.status).toBe(200);
      expect(fs.existsSync(deliveredSkill)).toBe(false);

      // 6. Remove the skill through the UI: the header's More actions menu
      //    holds Delete…, which opens a styled confirm dialog (no
      //    window.confirm); confirm via its destructive Delete skill button.
      await page.reload();
      await page
        .getByRole("button", { name: `More actions for ${skillName}` })
        .click();
      await page.getByRole("menuitem", { name: "Delete…" }).click();
      const confirmDialog = page.getByRole("dialog", {
        name: `Delete ${skillName}?`,
      });
      await expect(confirmDialog).toBeVisible();
      await confirmDialog.getByRole("button", { name: "Delete skill" }).click();

      // 7. The row vanishes from the library and the page returns to /skills.
      await expect(page).toHaveURL(/\/skills$/, { timeout: 10_000 });
      await expect(
        library.getByRole("link", { name: new RegExp(skillName) }),
      ).toHaveCount(0);
    } finally {
      // Best-effort teardown — leaks would compound across runs because the
      // e2e DB is shared.
      // Both routes address the uid. A lookup that finds nothing is the
      // resource already being gone, which is what this teardown wanted.
      const doomedSkill = await resolveResourceUid("skill", skillName);
      if (doomedSkill !== null)
        await bestEffortDelete(
          `http://127.0.0.1:${port}/api/v1/skills/${doomedSkill}`,
          token,
        );
      const doomedAgent = await resolveResourceUid("agent", agentName);
      if (doomedAgent !== null)
        await bestEffortDelete(
          `http://127.0.0.1:${port}/api/v1/agents/${doomedAgent}`,
          token,
        );
      try {
        fs.rmSync(skillSrc, { recursive: true, force: true });
        fs.rmSync(agentConfigDir, { recursive: true, force: true });
      } catch {
        // ignore
      }
    }
  },
);
