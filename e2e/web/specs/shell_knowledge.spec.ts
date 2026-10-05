// e2e/web/specs/shell_knowledge.spec.ts
//
// The one /knowledge page end-to-end, against a live daemon: create a
// collection and upload an item over the REST API, then walk the page in the
// real DOM — the collection in the tree, its document opened read-only, and
// the upload listed as a version on the document's History tab.
//
// Nothing auto-provisions a collection (spec knowledge "Create collections
// only deliberately"), so a walk starts by making one. A submitted item is
// written as a document on the spot, so the tree lists it at once, with no
// Inbox and no curation control; the page offers Tidy (or Copy prompt when no
// managed agent is available) in place of them.
//
// No acceptance marker: the spec's viewer and editor scenarios are pinned by
// the component tests, which assert the same actions far more precisely. What
// this adds is that the tree, the document and the vault's history agree with
// each other against a live daemon.

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
  const res = await page.request.post(`${base}/knowledge/collections`, {
    headers,
    data: { name, description },
  });
  expect(res.ok()).toBe(true);
  return (await res.json()) as { uid: string; name: string };
}

/** Submit a file the way the page's Upload does; it becomes a document at the
 *  collection root. */
async function submitItem(page: Page, collection: string, body: string) {
  const { base, headers } = api();
  const { "Content-Type": _json, ...multipartHeaders } = headers;
  const res = await page.request.post(`${base}/knowledge/upload`, {
    headers: multipartHeaders,
    multipart: {
      collection,
      file: {
        name: "top-level-note.md",
        mimeType: "text/markdown",
        buffer: Buffer.from(`# Top level note\n\n${body}\n`),
      },
    },
  });
  expect(res.ok()).toBe(true);
  return (await res.json()) as { path: string };
}

test("a collection is one tree; a document is read, opened in the editor and has a History tab", async ({
  page,
}) => {
  const name = `e2e-tree-${Date.now()}`;
  const collection = await createCollection(
    page,
    name,
    "An end-to-end collection",
  );
  const submitted = await submitItem(page, name, "The first body.");

  await page.goto("/knowledge");
  const tree = page.getByRole("navigation", {
    name: "Collections and documents",
  });
  await tree.getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await expect(page).toHaveURL(new RegExp(`/knowledge/${collection.uid}$`));
  await expect(page.getByText("An end-to-end collection")).toBeVisible();
  // No per-collection switch, no reach control, no search box.
  await expect(page.getByTestId("scope-control")).toHaveCount(0);
  await expect(page.getByRole("searchbox")).toHaveCount(0);

  // Written on the spot: a document in the tree, no Inbox, no curation control,
  // and Tidy all (Copy prompt with no managed agent) in the header.
  await expect(
    page.getByRole("button", { name: /^(Tidy all|Copy prompt)$/ }).first(),
  ).toBeVisible();
  await expect(tree.getByRole("button", { name: /^Inbox/ })).toHaveCount(0);
  await expect(page.getByTestId("knowledge-automatic")).toHaveCount(0);
  // The tree names a document by its file, as it is on disk.
  const fileName = submitted.path.split("/").pop() ?? "";
  await tree.getByRole("button", { name: fileName, exact: true }).click();
  await expect(page).toHaveURL(/\?file=/);
  await expect(page.getByText("The first body.")).toBeVisible();

  // The pane is read-only: Open in editor is a visible button, there is no Edit.
  await expect(
    page.getByRole("button", { name: "Open in editor", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Edit", exact: true }),
  ).toHaveCount(0);

  // History lists the upload as the document's one version, read from the
  // vault's history, with no restore offered on the current version.
  await page
    .getByRole("navigation", { name: "Document views" })
    .getByRole("link", { name: "History" })
    .click();
  await expect(page).toHaveURL(
    new RegExp(`/knowledge/${collection.uid}/history\\?file=`),
  );
  const versions = page.getByRole("list", { name: "Versions" });
  await expect(versions.getByRole("button")).toHaveCount(1);
  await expect(versions.getByRole("button").first()).toContainText("Current");
  await expect(
    page.getByRole("button", { name: "Restore this version…" }),
  ).toHaveCount(0);

  // The history card reaches the bottom of the window (the page is pinned to
  // it), not a 320px box with the rest of the pane left empty under it.
  const card = versions.locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]");
  const box = await card.boundingBox();
  const viewport = page.viewportSize();
  expect(box && viewport).toBeTruthy();
  expect(viewport!.height - (box!.y + box!.height)).toBeLessThan(40);
});
