// e2e/web/specs/shell_workflow.spec.ts
//
// The workflow surfaces end-to-end, against a live daemon on a vault that has
// never been touched.
//
// The isolated HOME the suite starts its daemon under is the one place a
// genuinely fresh vault exists, which is why seeding the built-in template
// (spec workflow "Seed one built-in template") is worth proving HERE
// rather than only in a unit test: the built-in template is seeded by a boot
// hook that reads the environment, writes a marker under ~/.coffer/state and
// goes through the resource framework. A unit test can hold the document
// against its parser; only this can say the daemon actually ran the hook and
// the page actually shows what it wrote.
//
// The second walk is the run surface. It stops short of starting a run: a
// started run dispatches a turn to a real agent, and this suite has none
// configured. What it pins is everything up to that point — a run exists, it
// is separate from the templates list, and its page shows the shape it froze.

import { expect, test } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken, resolveResourceUid } from "./_helpers";

beforeEachInjectToken();

/** The name the seed gives the built-in. A label, not an identity. */
const BUILTIN = "ship-a-change";

function api() {
  const { token, port } = readDaemonToken();
  return {
    base: `http://127.0.0.1:${port}/api/v1`,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
  };
}

acceptance(
  "workflow",
  "a vault that has never been touched already has a workflow",
  async ({ page }) => {
    await page.goto("/workflows");

    // On the page, where a developer looking for something to run would find
    // it — not merely in the database.
    // `exact` because the row also carries an "Enabled: <name>" switch and a
    // "Delete workflow: <name>" button, both of which contain the name.
    await expect(page.getByRole("cell", { name: BUILTIN, exact: true })).toBeVisible();

    // It is an ordinary resource of this kind: the framework gave it
    // an identity, and the same listing route every other kind answers on
    // answers for it.
    const uid = await resolveResourceUid("workflow", BUILTIN);
    expect(uid).not.toBeNull();

    // And it assumes nothing about this vault, which is the whole reason it
    // can be seeded at all: a task naming a skill would be refused at
    // validation on any machine that has not registered that skill.
    const { base, headers } = api();
    const resp = await page.request.get(`${base}/resources/${uid}`, { headers });
    const resource = (await resp.json()) as {
      config: { stages: Array<{ nodes: Array<{ skill: string | null }> }> };
    };
    const skills = resource.config.stages.flatMap((s) => s.nodes.map((n) => n.skill));
    expect(skills.every((s) => s === null || s === undefined)).toBe(true);
  },
);

acceptance(
  "workflow",
  "the web UI shows a delivery without opening its files by hand",
  async ({ page }) => {
    const { base, headers } = api();
    const uid = await resolveResourceUid("workflow", BUILTIN);
    const created = await page.request.post(`${base}/workflow/runs`, {
      headers,
      data: { template_uid: uid, title: "Buffer table for int64 userid" },
    });
    expect(created.ok()).toBe(true);
    const run = (await created.json()) as { id: string };

    // The runs list, which is NOT where the templates are: a template
    // is a resource and a run is operational state, and reaching either only
    // through the other is what this asserts against.
    await page.goto("/runs");
    await expect(
      page.getByRole("cell", { name: "Buffer table for int64 userid", exact: true }),
    ).toBeVisible();

    await page.goto(`/runs/${run.id}`);
    await expect(page.getByRole("heading", { name: "Buffer table for int64 userid" })).toBeVisible();

    // The shape it froze at creation, shown as stages and tasks — a map, with
    // the work laid out rather than a file to open.
    for (const stage of ["Understand", "Plan", "Implement", "Verify", "Report"]) {
      await expect(page.getByText(stage, { exact: false }).first()).toBeVisible();
    }
  },
);

test("a run's page offers nothing that advances or alters it", async ({ page }) => {
  // spec workflow "Offer no run controls on the run's page".
  // The run page is a map; retrying, redirecting and correcting are
  // said in a task's own conversation, where what is being decided is in front
  // of the developer. A button here would be a second place to drive the run,
  // and the two would disagree about what the developer meant.
  const { base, headers } = api();
  const uid = await resolveResourceUid("workflow", BUILTIN);
  const created = await page.request.post(`${base}/workflow/runs`, {
    headers,
    data: { template_uid: uid, title: "A run with no buttons" },
  });
  const run = (await created.json()) as { id: string };

  await page.goto(`/runs/${run.id}`);
  await expect(page.getByRole("heading", { name: "A run with no buttons" })).toBeVisible();

  for (const label of ["Start", "Pause", "Resume", "Retry", "Skip", "Send back"]) {
    await expect(page.getByRole("button", { name: label, exact: true })).toHaveCount(0);
  }
});
