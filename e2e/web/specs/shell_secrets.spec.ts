// e2e/web/specs/shell_secrets.spec.ts
//
// The Secrets page at /secrets against a real daemon. Adding a secret from the
// page (a label and a value) stores it at once under a minted id, with nothing
// to approve. A secret an MCP server cites opens on its own page naming that
// server under Used by, and Delete then says what still uses it instead of
// deleting; an unused secret is deleted from its ⋯ menu. Those
// two store a resource-style ref (`e2e/<name>`). Only data this file creates is
// touched, and each test removes it.
//
// Reveal and Approve need the desktop app's presence check, so a browser only
// shows them disabled; the reveal itself and the missing-on-this-Mac state are
// covered in frontend/src/pages/SecretsPage.test.tsx, where the daemon's
// answers can be fixed.

import { expect, test, type Page } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import {
  beforeEachInjectToken,
  deregisterMcpServer,
  generateUniqueName,
  readDaemonToken,
} from "./_helpers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const PYTHON = path.join(REPO_ROOT, ".venv/bin/python3");
const FAKE_SERVER = path.join(
  REPO_ROOT,
  "backend/tests/fixtures/fake_mcp_server.py",
);

beforeEachInjectToken();

function api(pathname: string, init: RequestInit = {}): Promise<Response> {
  const { token, port } = readDaemonToken();
  return fetch(`http://127.0.0.1:${port}/api/v1${pathname}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
      ...(init.headers ?? {}),
    },
  });
}

/** The id Coffer minted for each secret a spec stored, by the name it gave. */
const minted = new Map<string, string>();
const refOf = (name: string) => {
  const ref = minted.get(name);
  if (!ref) throw new Error(`no secret stored as ${name}`);
  return ref;
};

/** Store a secret named `name`; Coffer mints its id (`secret/<hex>`). */
async function storeSecret(name: string, value: string): Promise<void> {
  const r = await api("/secrets", {
    method: "POST",
    body: JSON.stringify({ label: name, value }),
  });
  if (!r.ok) throw new Error(`store failed: ${r.status} ${await r.text()}`);
  minted.set(name, ((await r.json()) as { ref: string }).ref);
}

/** Best-effort cleanup: a secret already gone, or never stored, is fine. */
async function deleteSecret(name: string): Promise<void> {
  const ref = minted.get(name);
  if (ref) await api(`/secrets/${ref}`, { method: "DELETE" });
}

async function registerCitingServer(
  server: string,
  secret: string,
): Promise<void> {
  const r = await api("/resources", {
    method: "POST",
    body: JSON.stringify({
      kind: "mcp_server",
      name: server,
      config: {
        transport: {
          type: "stdio",
          command: PYTHON,
          args: [FAKE_SERVER, "--scenario", "basic", "--tools", "read_file"],
          secret_refs: { E2E_TOKEN: refOf(secret) },
        },
      },
    }),
  });
  if (!r.ok) throw new Error(`register failed: ${r.status} ${await r.text()}`);
}

/** Refuse what waits on `ref`. A secret sent somewhere new waits for approval
 *  in the desktop app, and the approvals
 *  window a browser opens for it would cover this page and every later spec's.
 *  Rejecting withholds the value; the citation, which is what this spec reads,
 *  stays. */
async function rejectApprovalsFor(ref: string): Promise<void> {
  const r = await api("/secrets/approvals?status=pending");
  const { approvals } = (await r.json()) as {
    approvals: { id: string; ref: string | null }[];
  };
  for (const a of approvals.filter((x) => x.ref === ref)) {
    await api(`/secrets/approvals/${a.id}/reject`, { method: "POST" });
  }
}

/** The list pane's link for a secret, found by the name it is shown under. */
const listLink = (page: Page, text: string) =>
  page
    .getByRole("group", { name: "Secrets" })
    .getByRole("link")
    .filter({ hasText: text });

/** Where a secret's own page lives. */
const pageOf = (ref: string) => `/secrets/${encodeURIComponent(ref)}`;

test("adding a secret stores it at once under a minted id, with nothing to approve", async ({
  page,
}) => {
  const label = generateUniqueName("e2e-secret");
  let id = "";
  try {
    await page.goto("/secrets");
    await expect(
      page.getByRole("heading", { name: /^Secrets$/ }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Add secret" }).first().click();
    const dialog = page.getByRole("dialog", { name: "Add secret" });
    // A label and a value: no name to type.
    await dialog.getByLabel("Name").fill(label);
    await dialog.getByLabel("Value").fill("e2e-not-a-real-value");
    await dialog.getByRole("button", { name: "Add secret" }).click();
    // The minted URI is offered to copy, and the dialog — now titled for what
    // it added — waits for Done.
    const added = page.getByRole("dialog", { name: `Added ${label}` });
    const uri = added.getByText(/^coffer:\/\/secret\/[0-9a-f]{32}$/);
    await expect(uri).toBeVisible();
    id = ((await uri.textContent()) ?? "").replace("coffer://secret/", "");
    await added.getByRole("button", { name: "Done" }).click();
    await expect(added).toBeHidden();

    // It is listed by its label, no approval waits, and no value is on the page.
    await expect(listLink(page, label)).toBeVisible();
    await expect(page.getByText(/Saved, waiting for approval/)).toHaveCount(0);
    await expect(page.getByText("e2e-not-a-real-value")).toHaveCount(0);
  } finally {
    if (id) await api(`/secrets/secret/${id}`, { method: "DELETE" });
  }
});

test("a secret an MCP server cites names it, and Delete says so instead of deleting", async ({
  page,
}) => {
  const secret = generateUniqueName("e2e-secret");
  const server = generateUniqueName("e2esecretsrv");
  try {
    await storeSecret(secret, "e2e-not-a-real-value");
    await registerCitingServer(server, secret);
    await rejectApprovalsFor(refOf(secret));

    // A row in the list, shown by the secret's name, opens it on its own page.
    await page.goto("/secrets");
    await listLink(page, secret).click();
    await expect(page).toHaveURL(new RegExp(`${pageOf(refOf(secret))}$`));
    const usedBy = page.getByRole("region", { name: "Used by" });
    await expect(usedBy).toContainText(server);

    await page
      .getByRole("button", { name: `Actions for ${refOf(secret)}` })
      .click();
    await page.getByRole("menuitem", { name: "Delete…" }).click();
    const blocked = page.getByRole("dialog", { name: /is in use$/ });
    await expect(blocked).toContainText(server);
    await expect(blocked).toContainText("MCP server");
    // The dialog only names what still reads the secret: it offers no delete,
    // and each citer has an Open link to its page.
    await expect(
      blocked.getByRole("button", { name: "Delete secret" }),
    ).toHaveCount(0);
    await expect(blocked.getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      `/mcp-servers/${server}`,
    );
    await blocked.getByRole("button", { name: "Close" }).last().click();
    await expect(usedBy).toBeVisible();

    // The citer, in Used by, opens that server's page.
    await usedBy.getByRole("link", { name: new RegExp(server) }).click();
    await expect(page).toHaveURL(new RegExp(`/mcp-servers/${server}$`));
  } finally {
    await rejectApprovalsFor(refOf(secret));
    await deregisterMcpServer(server);
    await deleteSecret(secret);
  }
});

test("an unused secret is deleted from its menu", async ({ page }) => {
  const name = generateUniqueName("e2e-secret");
  try {
    await storeSecret(name, "e2e-not-a-real-value");
    await page.goto(pageOf(refOf(name)));
    // Nothing cites it.
    await expect(page.getByRole("region", { name: "Used by" })).toContainText(
      "Nothing",
    );

    // A browser cannot run the presence check, so Reveal names the app.
    await expect(
      page.getByRole("button", { name: "Reveal in the Coffer app" }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: `Actions for ${refOf(name)}` })
      .click();
    await page.getByRole("menuitem", { name: "Delete…" }).click();
    const confirm = page.getByRole("dialog", { name: /^Delete .*\?$/ });
    await confirm.getByRole("button", { name: "Delete secret" }).click();
    await expect(confirm).toBeHidden();
    await expect(page).toHaveURL(/\/secrets$/);
    await expect(listLink(page, name)).toHaveCount(0);
  } finally {
    await deleteSecret(name);
  }
});
