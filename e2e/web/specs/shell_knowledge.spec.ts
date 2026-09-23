// e2e/web/specs/shell_knowledge.spec.ts
//
// The one /knowledge surface end-to-end: create a collection over the REST
// API, put material in it, then walk its single tree of documents in the real
// DOM.
//
// Nothing auto-provisions a collection any more (spec knowledge FR-008), so a
// walk starts by making one. State is provisioned through the daemon's REST API
// so the tests stay robust against UI churn; the page render is exercised
// against the real DOM.
//
// Material either waits in the collection's hidden inbox for a curation pass or
// — with no internal model configured, which is how the e2e daemon runs — is
// promoted to a document on the spot. The walk below reads the submission's
// status and asserts whichever outcome the daemon reported, so it holds in both
// configurations.
//
// No acceptance marker: the spec's viewer scenario is pinned by the component
// test, which can assert the same actions on every document far more precisely
// than a browser walk can. What this adds is that the tree, the pending hint
// and the REST write agree with each other against a live daemon.

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

/** Submit MATERIAL. Where it lands is the layer's decision, never a caller's. */
async function submitMaterial(
  page: Page,
  collection: string,
  title: string,
  description: string,
  body: string,
): Promise<{ status: "pending" | "written"; path: string | null }> {
  const { base, headers } = api();
  const res = await page.request.post(`${base}/knowledge/material`, {
    headers,
    data: { collection, title, description, body },
  });
  expect(res.ok()).toBe(true);
  return (await res.json()) as {
    status: "pending" | "written";
    path: string | null;
  };
}

test("the collection is one tree of documents, with no lanes to switch", async ({
  page,
}) => {
  const name = `e2e-tree-${Date.now()}`;
  await page.goto("/knowledge");
  await createCollection(page, name, "An end-to-end collection");
  const submitted = await submitMaterial(
    page,
    name,
    "Top level note",
    "a first fact",
    "body",
  );

  await page.reload();
  await expect(page.getByText(name)).toBeVisible();
  await expect(page.getByText("An end-to-end collection")).toBeVisible();

  await page.getByText(name).first().click();

  // One tree, no tabs: the sources/topics split is gone.
  await expect(page.getByRole("tab")).toHaveCount(0);

  if (submitted.status === "written") {
    // Promoted on the spot: it is a document now, in the tree, and opening it
    // offers the same actions as any other document.
    await page.getByRole("button", { name: "Top level note" }).click();
    await expect(page.getByText(submitted.path ?? "")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /delete document/i }),
    ).toBeVisible();
  } else {
    // Waiting in the inbox: not a document yet, and the page says so.
    await expect(
      page.getByText(/being merged into the documents/i),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Top level note" }),
    ).toHaveCount(0);
  }
});
