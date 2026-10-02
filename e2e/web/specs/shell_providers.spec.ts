// e2e/web/specs/shell_providers.spec.ts
//
// The Model providers page against the real daemon: one list + detail (the
// detail one column, no tabs), Used by naming Coffer's engine once the provider carries
// it (and linking Settings › General), Edit renaming in place, and Delete —
// blocked while the provider is the engine's, done for an unused one.
//
// Every provider here is created through the REST API with a loopback base
// URL nothing listens on (127.0.0.1:9, the discard port) and a throwaway key,
// so the endpoint probe fails fast and no request leaves the machine. Each
// test removes what it made.
import { expect, test, type Page } from "@playwright/test";

import {
  beforeEachInjectToken,
  generateUniqueName,
  readDaemonToken,
} from "./_helpers";

beforeEachInjectToken();

async function api(
  method: string,
  route: string,
  body?: unknown,
): Promise<Response> {
  const { token, port } = readDaemonToken();
  return fetch(`http://127.0.0.1:${port}/api/v1${route}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** Create a keyed provider on a dead loopback port; returns its uid. */
async function seedProvider(name: string): Promise<string> {
  const r = await api("POST", "/providers", {
    name,
    protocol: "openai",
    base_url: "http://127.0.0.1:9/v1",
    secret_value: `sk-e2e-${Date.now().toString(36)}`,
  });
  if (!r.ok)
    throw new Error(`create provider failed: ${r.status} ${await r.text()}`);
  return ((await r.json()) as { uid: string }).uid;
}

async function removeProvider(uid: string): Promise<void> {
  try {
    await api("DELETE", `/providers/${uid}`);
  } catch {
    // best-effort
  }
}

/** The list pane's row for a provider. */
const row = (page: Page, name: string) =>
  page.getByTestId("provider-row").filter({ hasText: name });

test("the list opens a provider as one column, addressed by its uid", async ({
  page,
}) => {
  const name = generateUniqueName("e2eprov");
  const uid = await seedProvider(name);
  try {
    await page.goto("/model-providers");
    await expect(
      page.getByRole("heading", { name: "Model providers" }),
    ).toBeVisible();
    await row(page, name).click();
    await expect(page).toHaveURL(new RegExp(`/model-providers/${uid}$`));
    await expect(page.getByRole("heading", { name, level: 2 })).toBeVisible();
    await expect(row(page, name)).toHaveAttribute("aria-current", "page");
    // The endpoint and the key's secret reference, never the key.
    await expect(page.getByText("http://127.0.0.1:9/v1").first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Replace key" }),
    ).toBeVisible();

    // One column, no tabs: Used by, Endpoint, Models.
    await expect(page.getByRole("tab")).toHaveCount(0);
    for (const section of ["Used by", "Endpoint", "Models"]) {
      await expect(
        page.getByRole("heading", { name: section, level: 3 }),
      ).toBeVisible();
    }
    // Nothing listens on the discard port: the listing says so and offers Retry.
    await expect(
      page.getByText("Couldn't list this endpoint's models"),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();

    // A deep link lands on the same provider.
    await page.goto(`/model-providers/${uid}`);
    await expect(page.getByRole("heading", { name, level: 2 })).toBeVisible();
  } finally {
    await removeProvider(uid);
  }
});

test("Used by names Coffer's engine and links Settings › General; Delete is blocked", async ({
  page,
}) => {
  const name = generateUniqueName("e2eengine");
  const uid = await seedProvider(name);
  try {
    const r = await api("POST", `/providers/${uid}/internal-default`);
    expect(r.ok).toBeTruthy();

    await page.goto(`/model-providers/${uid}`);
    const usedBy = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Used by" }),
    });
    const engine = usedBy.getByRole("button", { name: /Coffer's engine/ });
    await expect(engine).toBeVisible();
    await expect(
      row(page, name).getByRole("img", { name: "Coffer · background model" }),
    ).toBeVisible();

    // While the engine runs on it, Delete names that and stays disabled.
    await page
      .getByRole("button", { name: `More actions for ${name}` })
      .click();
    await page.getByRole("menuitem", { name: "Delete provider" }).click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByText(new RegExp(`${name} is in use`)),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Delete provider" }),
    ).toBeDisabled();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();

    await engine.click();
    await expect(page).toHaveURL(/\/settings\/general$/);
  } finally {
    await removeProvider(uid);
  }
});

test("Edit renames the provider in place", async ({ page }) => {
  const name = generateUniqueName("e2erename");
  const renamed = `${name}-eu`;
  const uid = await seedProvider(name);
  try {
    await page.goto(`/model-providers/${uid}`);
    await page.getByRole("button", { name: "Edit" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name").fill(renamed);
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();
    // Same address — the page is keyed by uid — under the new label.
    await expect(page).toHaveURL(new RegExp(`/model-providers/${uid}$`));
    await expect(
      page.getByRole("heading", { name: renamed, level: 2 }),
    ).toBeVisible();
    await expect(row(page, renamed)).toBeVisible();
  } finally {
    await removeProvider(uid);
  }
});

test("an unused provider is deleted after a confirmation", async ({ page }) => {
  const name = generateUniqueName("e2edelete");
  const uid = await seedProvider(name);
  try {
    await page.goto(`/model-providers/${uid}`);
    await page
      .getByRole("button", { name: `More actions for ${name}` })
      .click();
    await page.getByRole("menuitem", { name: "Delete provider" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Delete provider" }).click();
    await expect(dialog).toBeHidden();
    await expect(page).not.toHaveURL(new RegExp(uid));
    await expect(row(page, name)).toHaveCount(0);
    const gone = await api("GET", `/providers/${uid}`);
    expect(gone.status).toBe(404);
  } finally {
    await removeProvider(uid);
  }
});
