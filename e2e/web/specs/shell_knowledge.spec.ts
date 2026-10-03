// e2e/web/specs/shell_knowledge.spec.ts
//
// The one /knowledge page end-to-end, against a live daemon: create a
// collection and upload an item over the REST API, then walk the page in the
// real DOM — the collection in the tree, its document opened, an edit saved
// through the body-only editor, the save in the document's History tab and in
// Recent changes.
//
// Nothing auto-provisions a collection (spec knowledge "Create collections
// only deliberately"), so a walk starts by making one. The e2e daemon runs
// without Coffer's model, so a submitted item is written as a document on the
// spot (`pending` false) and the page shows no Inbox and no Curate now — the
// no-model line instead; the walk reads the upload's `pending` flag and asserts
// whichever the daemon reported, so it holds in both configurations.
//
// No acceptance marker: the spec's viewer and editor scenarios are pinned by
// the component tests, which assert the same actions far more precisely. What
// this adds is that the tree, the editor's save and the vault's history agree
// with each other against a live daemon.

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

/** Submit an ITEM the way the page's Upload does (agents write a file into
 *  `.inbox/` instead). Where it lands is the layer's decision, never a caller's. */
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
  return (await res.json()) as {
    pending: boolean;
    path: string | null;
  };
}

test("a collection is one tree; a document is read, edited and shows up in its History", async ({
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

  if (submitted.pending) {
    // Waiting in the Inbox: not a document yet.
    await expect(tree.getByRole("button", { name: /Inbox/ })).toContainText(
      "1",
    );
    return;
  }

  // Written on the spot (no model): a document in the tree, and the page says
  // how items become documents instead of offering an Inbox.
  await expect(
    page.getByText(
      /Set Coffer's model to curate new items into your documents/,
    ),
  ).toBeVisible();
  await expect(tree.getByRole("button", { name: /^Inbox/ })).toHaveCount(0);
  // The tree names a document by its file, as it is on disk.
  const fileName = (submitted.path ?? "").split("/").pop() ?? "";
  await tree.getByRole("button", { name: fileName, exact: true }).click();
  await expect(page).toHaveURL(/\?file=/);
  await expect(page.getByText("The first body.")).toBeVisible();

  // The body-only editor: title and description read-only above it.
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.getByRole("textbox", { name: `Edit ${submitted.path}` });
  await expect(editor).toBeVisible();
  await expect(page.getByText("Kept by curation")).toBeVisible();
  await editor.fill("The edited body.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("The edited body.")).toBeVisible();

  // The save is a version naming you, in the document's History.
  await page.getByRole("link", { name: /^History/ }).click();
  await expect(page).toHaveURL(
    new RegExp(`/knowledge/${collection.uid}/history\\?file=`),
  );
  await expect(page.getByText("newest first")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^You.*Current/ }),
  ).toBeVisible();

  // …and on the cross-collection timeline.
  await page
    .getByRole("link", { name: /Recent changes/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/knowledge$/);
  await expect(page.getByText("edited", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByRole("link", { name: fileName, exact: true }).first(),
  ).toBeVisible();
});
