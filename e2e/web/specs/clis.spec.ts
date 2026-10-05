// e2e/web/specs/clis.spec.ts
//
// The CLIs page against a real daemon (spec web-ui "Show every CLI a skill
// requires on the CLIs page"). A throwaway skill declares two commands under
// `requires:` — one that cannot exist and `sh`, which always does — and is
// imported over REST. The test then walks the list (Needs you before Ready),
// the command's pane and its hand-off (Hand off to <Agent> where a managed
// agent is installed, else Copy prompt — an e2e run installs nothing) and the
// skill's Requires tab. The skill is removed afterwards. The scenarios'
// markers are on the unit tests (ClisPage.test.tsx, SkillRequiresTab.test.tsx).

import { expect, test } from "@playwright/test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  beforeEachInjectToken,
  readDaemonToken,
  resolveResourceUid,
} from "./_helpers";

beforeEachInjectToken();

const MISSING = "coffer-e2e-missing-cmd";

function mkRequiringSkill(name: string): string {
  const dir = path.join(os.tmpdir(), `coffer-e2e-skill-${name}-${Date.now()}`);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, "SKILL.md"),
    [
      "---",
      `name: ${name}`,
      `description: e2e skill ${name} that requires two commands.`,
      "requires:",
      `  - command: ${MISSING}`,
      "    title: Coffer e2e missing command",
      "    why: The e2e suite checks the missing-command path with it.",
      "  - sh",
      "---",
      "",
      "body",
      "",
    ].join("\n"),
    "utf-8",
  );
  return dir;
}

test("the CLIs page lists what a skill requires, and hands a fix to an agent", async ({
  page,
}) => {
  const { token, port } = readDaemonToken();
  const skillName = `e2e-requires-${Date.now().toString(36)}`;
  const src = mkRequiringSkill(skillName);
  const headers = {
    "Content-Type": "application/json",
    "X-Coffer-Token": token,
    "X-Coffer-Actor": "e2e",
  };
  try {
    const imported = await fetch(
      `http://127.0.0.1:${port}/api/v1/skills/import`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ path: src }),
      },
    );
    expect(imported.status).toBe(201);
    // Probe afresh so the rows reflect the skill just imported.
    const checked = await fetch(`http://127.0.0.1:${port}/api/v1/clis/check`, {
      method: "POST",
      headers,
    });
    expect(checked.status).toBe(200);

    // 1. The list: the missing command under Needs attention, the ready one under Ready.
    await page.goto("/clis");
    await expect(page.getByRole("heading", { name: "CLIs" })).toBeVisible();
    const needsYou = page.getByRole("region", { name: "Needs attention" });
    const ready = page.getByRole("region", { name: "Ready" });
    const missingRow = needsYou
      .getByRole("button")
      .filter({ hasText: MISSING });
    await expect(missingRow).toBeVisible({ timeout: 10_000 });
    await expect(missingRow).toContainText("Not found");
    await expect(
      ready
        .getByRole("button")
        .filter({ has: page.locator(".font-mono", { hasText: /^sh$/ }) }),
    ).toBeVisible();

    // 2. Its pane: the banner names the skill it breaks, and the header's one
    //    action hands the fix to an agent — nothing installs.
    await missingRow.click();
    await expect(page).toHaveURL(new RegExp(`/clis/${MISSING}$`));
    const banner = page.getByTestId("cli-problem");
    await expect(banner).toContainText(`${MISSING} isn’t found on this machine`);
    await expect(banner).toContainText(skillName);
    await expect(page.getByText("Not on PATH")).toBeVisible();
    // The hand-off is the split button Hand off to <Agent> when a managed agent
    // is installed on the runner, and a plain Copy prompt button when none is.
    await expect(
      page.getByRole("button", { name: /^(Hand off to .+|Copy prompt)$/ }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Ask an agent" })).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /Install|Update/ }),
    ).toHaveCount(0);

    // 3. Needed by → the skill's Requires tab, whose rows link back to /clis/<command>.
    await page.getByRole("link", { name: skillName }).click();
    await expect(page).toHaveURL(new RegExp(`/skills/${skillName}/requires$`));
    // Each requirement is a row whose "View in CLIs" link opens /clis/<command>.
    const requires = page.getByRole("tabpanel", { name: "Requires" });
    await expect(
      requires.getByRole("link", { name: "View in CLIs" }),
    ).toHaveCount(2);
    await expect(requires.locator(`a[href="/clis/${MISSING}"]`)).toBeVisible();
    await expect(requires.locator('a[href="/clis/sh"]')).toBeVisible();
    await requires.locator('a[href="/clis/sh"]').click();
    await expect(page).toHaveURL(/\/clis\/sh$/);
    await expect(
      page.getByRole("heading", { name: "sh", exact: true }),
    ).toBeVisible();
  } finally {
    const uid = await resolveResourceUid("skill", skillName);
    if (uid !== null) {
      await fetch(`http://127.0.0.1:${port}/api/v1/resources/${uid}`, {
        method: "DELETE",
        headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
      }).catch(() => undefined);
    }
    fs.rmSync(src, { recursive: true, force: true });
  }
});
