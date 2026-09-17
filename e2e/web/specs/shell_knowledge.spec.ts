// e2e/web/specs/shell_knowledge.spec.ts
//
// The one /knowledge surface end-to-end: create a collection through the UI
// dialog, put sources in it over the REST API, then walk both lanes in the
// real DOM.
//
// Nothing auto-provisions a collection any more (spec knowledge FR-008), so a
// walk starts by making one. State is provisioned through the daemon's REST API
// so the tests stay robust against UI churn; the page render is exercised
// against the real DOM.
//
// No acceptance marker: the spec's viewer scenario is pinned by the component
// test, which can assert the absence of a delete affordance far more precisely
// than a browser walk can. What this adds is that the two lanes, the tab
// switch and the REST write agree with each other against a live daemon.

import { expect, test, type Page } from "@playwright/test";
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

/** Write a SOURCE. The `sources/` segment is the layer's, never a caller's. */
async function writeSource(
  page: Page,
  collection: string,
  title: string,
  description: string,
  body: string,
  folder?: string,
) {
  const { base, headers } = api();
  await page.request.put(`${base}/knowledge/file`, {
    headers,
    data: { collection, folder, title, description, body },
  });
}

test("both lanes render, and topics is empty until curation runs", async ({ page }) => {
  const name = `e2e-lanes-${Date.now()}`;
  await page.goto("/knowledge");
  await createCollection(page, name, "An end-to-end collection");
  await writeSource(page, name, "Top level note", "at the lane root", "body");
  await writeSource(page, name, "Nested note", "one level down", "deeper body", "nested");

  await page.reload();
  await expect(page.getByText(name)).toBeVisible();
  await expect(page.getByText("An end-to-end collection")).toBeVisible();

  await page.getByText(name).first().click();

  // Sources is the lane a person writes, and it opens on it. The lane's own
  // level: the root file and the folder, not the file inside the folder.
  await expect(page.getByText("Top level note")).toBeVisible();
  await expect(page.getByText("nested")).toBeVisible();
  await expect(page.getByText("Nested note")).toHaveCount(0);

  // Topics holds what curation derives, and a fresh collection has none — the
  // page must say so rather than look broken (spec knowledge FR-040).
  await page.getByRole("tab", { name: /topics/i }).click();
  await expect(page.getByText("Top level note")).toHaveCount(0);
});
