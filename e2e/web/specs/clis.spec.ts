// e2e/web/specs/clis.spec.ts
//
// The CLIs page against a real daemon (spec web-ui "Show every CLI a skill
// requires on the CLIs page"). A throwaway skill declares two commands under
// `requires:` — one that cannot exist and `sh`, which always does — and is
// imported over REST. The test then walks the list (Needs you before Ready),
// the command's pane and its hand-off (Copy prompt, and Ask an agent opening
// the draft with the prompt in its composer — never sent: an e2e run installs
// nothing) and the skill's Requires tab. A stand-in `codex` on the daemon's PATH makes a
// managed agent available. The skill is removed afterwards. The scenarios'
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

function home(): string {
  const pointer =
    process.env.COFFER_E2E_HOME_FILE ?? "/tmp/coffer-e2e-home.path";
  return fs.readFileSync(pointer, "utf-8").trim();
}

/** A stand-in `codex` on the daemon's PATH, so a managed agent is available. */
function ensureCodexProgram(): void {
  const bin = path.join(home(), "bin");
  fs.mkdirSync(bin, { recursive: true });
  const program = path.join(bin, "codex");
  if (!fs.existsSync(program)) {
    fs.writeFileSync(program, '#!/bin/sh\necho "codex-cli 0.41.0"\n', {
      mode: 0o755,
    });
  }
}

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
  ensureCodexProgram();
  const { token, port } = readDaemonToken();
  const skillName = `e2e-requires-${Date.now().toString(36)}`;
  const src = mkRequiringSkill(skillName);
  const headers = {
    "Content-Type": "application/json",
    "X-Coffer-Token": token,
    "X-Coffer-Actor": "e2e",
  };
  const conversationCount = async (): Promise<number> => {
    const res = await fetch(
      `http://127.0.0.1:${port}/api/v1/chat/conversations`,
      { headers },
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { conversations: unknown[] };
    return body.conversations.length;
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

    // 1. The list: the missing command under Needs you, the ready one under Ready.
    await page.goto("/clis");
    await expect(page.getByRole("heading", { name: "CLIs" })).toBeVisible();
    const needsYou = page.getByRole("region", { name: "Needs you" });
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
    await expect(page.getByTestId("nav-dot-clis")).toBeVisible();

    // 2. Its pane: the banner names the skill it breaks, and the header's one
    //    action hands the fix to an agent — nothing installs.
    await missingRow.click();
    await expect(page).toHaveURL(new RegExp(`/clis/${MISSING}$`));
    const banner = page.getByTestId("cli-problem");
    await expect(banner).toContainText(`${MISSING} isn't installed`);
    await expect(banner).toContainText(skillName);
    await expect(page.getByText("Not on PATH")).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy prompt" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Install|Update/ }),
    ).toHaveCount(0);

    // Ask an agent → New conversation → the draft, the prompt in its composer.
    const before = await conversationCount();
    await page.getByRole("button", { name: "Ask an agent" }).click();
    const dialog = page.getByRole("dialog", { name: /new conversation/i });
    const start = dialog.getByRole("button", { name: /^start$/i });
    await expect(start).toBeEnabled();
    await start.click();
    await expect(page).toHaveURL(/\/conversations\/new$/);
    const box = page.getByRole("textbox", { name: /message input/i });
    await expect(box).toHaveValue(
      new RegExp(`Please install the command-line tool \`${MISSING}\``),
    );
    // Pre-filled, never sent: still the draft, and no conversation was created.
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/\/conversations\/new$/);
    expect(await conversationCount()).toBe(before);
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`/clis/${MISSING}$`));

    // 3. Needed by → the skill's Requires tab, whose rows link back to /clis/<command>.
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
