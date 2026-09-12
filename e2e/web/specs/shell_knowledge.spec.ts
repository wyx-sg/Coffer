// e2e/web/specs/shell_knowledge.spec.ts
//
// The one /knowledge surface end-to-end: create a collection through the UI
// dialog, put a file in it over the REST API, then walk the catalogue and read
// the file in the real DOM.
//
// Nothing auto-provisions a collection any more (spec knowledge FR-010), so a
// walk starts by making one. State is provisioned through the daemon's REST API
// so the tests stay robust against UI churn; the page render is exercised
// against the real DOM.

import { expect, type Page } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

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

async function createCollection(page: Page, name: string, description: string) {
  const { base, headers } = api();
  await page.request.post(`${base}/knowledge/collections`, {
    headers,
    data: { name, description },
  });
}

async function writeFile(
  page: Page,
  directory: string,
  title: string,
  description: string,
  body: string,
) {
  const { base, headers } = api();
  await page.request.put(`${base}/knowledge/file`, {
    headers,
    data: { directory, title, description, body },
  });
}

acceptance("knowledge", "the catalogue lists one level of a collection", async ({ page }) => {
  const name = `e2e-catalogue-${Date.now()}`;
  await page.goto("/knowledge");
  await createCollection(page, name, "An end-to-end collection");
  await writeFile(page, name, "Top level note", "at the collection root", "body");
  await writeFile(page, `${name}/nested`, "Nested note", "one level down", "deeper body");

  await page.reload();
  await expect(page.getByText(name)).toBeVisible();
  await expect(page.getByText("An end-to-end collection")).toBeVisible();

  await page.getByText(name).first().click();
  // The collection's own level: the root file and the folder, not the file
  // inside the folder — the catalogue descends a level per request (FR-021).
  await expect(page.getByText("Top level note")).toBeVisible();
  await expect(page.getByText("nested")).toBeVisible();
  await expect(page.getByText("Nested note")).toHaveCount(0);
});
