// e2e/web/specs/clis.spec.ts
//
// The CLIs page against a real daemon (spec web-ui "Show every CLI a skill
// requires on the CLIs page"). A throwaway skill declares two commands under
// `requires:` — one that cannot exist (with a Homebrew formula, so it is
// installable) and `sh`, which always does — and is imported over REST. The
// test then walks the list (problems first), the detail page, the Homebrew
// confirmation (CANCELLED: an e2e run never installs anything) and the skill's
// Requires tab. The skill is removed afterwards.
//
// scenario (web-ui, revise-web-ui-ia 7.14d): "the CLIs page lists problems first"
// scenario (web-ui, revise-web-ui-ia 7.14d): "installing a CLI asks first and uses Homebrew only"
// scenario (web-ui, revise-web-ui-ia 7.14d): "a skill's requirement links to its CLI"

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
      `    brew: ${MISSING}`,
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

test("the CLIs page lists what a skill requires, and Install asks first", async ({
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

    // 1. The list: the missing command before the ready one.
    await page.goto("/clis");
    await expect(page.getByRole("heading", { name: "CLIs" })).toBeVisible();
    const missingRow = page.getByRole("row").filter({ hasText: MISSING });
    const shRow = page
      .getByRole("row")
      .filter({ has: page.locator(".font-mono", { hasText: /^sh$/ }) });
    await expect(missingRow).toBeVisible({ timeout: 10_000 });
    await expect(missingRow).toContainText("Not on PATH");
    await expect(missingRow).toContainText("Not found");
    await expect(shRow).toContainText("Ready");
    const commands = await page
      .locator("tbody tr td:first-child .font-mono")
      .allTextContents();
    expect(commands.indexOf(MISSING)).toBeGreaterThanOrEqual(0);
    expect(commands.indexOf(MISSING)).toBeLessThan(commands.indexOf("sh"));
    await expect(page.getByTestId("nav-dot-clis")).toBeVisible();

    // 2. Install… opens the confirmation naming the exact Homebrew command —
    //    and is cancelled: nothing may run.
    await missingRow.getByRole("button", { name: "Install…" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(`Install ${MISSING}?`)).toBeVisible();
    await expect(dialog.getByTestId("cli-install-command")).toHaveText(
      `brew install ${MISSING}`,
    );
    await expect(dialog.getByText("Homebrew", { exact: true })).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: `Run brew install ${MISSING}` }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
    const job = await fetch(
      `http://127.0.0.1:${port}/api/v1/clis/${MISSING}/install`,
      { headers },
    );
    expect(job.status).toBe(404); // no install ever ran

    // 3. The detail page: the problem banner names the skill it breaks.
    await missingRow.locator("td").first().click();
    await expect(page).toHaveURL(new RegExp(`/clis/${MISSING}$`));
    await expect(page.getByTestId("cli-problem")).toContainText(
      `${MISSING} isn't installed`,
    );
    await expect(page.getByTestId("cli-problem")).toContainText(skillName);
    await expect(page.getByText(`brew install ${MISSING}`)).toBeVisible();

    // 4. Needed by → the skill's Requires tab, whose rows link back to /clis/<command>.
    await page.getByRole("link", { name: skillName }).click();
    await expect(page).toHaveURL(new RegExp(`/skills/${skillName}/requires$`));
    const requires = page.getByRole("list", { name: "Requires" });
    await expect(requires.getByRole("link", { name: MISSING })).toHaveAttribute(
      "href",
      `/clis/${MISSING}`,
    );
    await expect(
      requires.getByRole("link", { name: "sh", exact: true }),
    ).toHaveAttribute("href", "/clis/sh");
    await requires.getByRole("link", { name: "sh", exact: true }).click();
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
