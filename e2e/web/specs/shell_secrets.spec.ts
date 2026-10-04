// e2e/web/specs/shell_secrets.spec.ts
//
// The Secrets page at /secrets against a real daemon. Adding a secret from the
// page stores it at once, with nothing to approve. A secret an MCP server cites
// lists under In use naming that server, and Delete then says what still uses
// it instead of deleting; an unused secret is deleted from its ⋯ menu. Those
// two store a resource-style ref (`e2e/<name>`). Only data this file creates is
// touched, and each test removes it.
//
// Reveal and Approve need the desktop app's presence check, so a browser only
// shows them disabled; the reveal itself and the missing-on-this-Mac state are
// covered in frontend/src/pages/SecretsPage.test.tsx, where the daemon's
// answers can be fixed.

import { expect, test } from "@playwright/test";
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

/** A ref nothing has sent anywhere and that is not a standalone secret:
 *  stored at once, with no approval. */
const refOf = (name: string) => `e2e/${name}`;

async function storeSecret(name: string, value: string): Promise<void> {
  const r = await api("/secrets", {
    method: "POST",
    body: JSON.stringify({ ref: refOf(name), value }),
  });
  if (!r.ok) throw new Error(`store failed: ${r.status} ${await r.text()}`);
}

/** Best-effort cleanup: a secret already gone is fine. */
async function deleteSecret(name: string): Promise<void> {
  await api(`/secrets/e2e/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
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

test("adding a secret stores it at once, with nothing to approve", async ({
  page,
}) => {
  const name = generateUniqueName("e2e-secret");
  try {
    await page.goto("/secrets");
    await expect(
      page.getByRole("heading", { name: /^Secrets$/ }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Add secret" }).first().click();
    const dialog = page.getByRole("dialog", { name: "Add secret" });
    await dialog.getByLabel("Name").fill(name);
    await dialog.getByLabel("Value").fill("e2e-not-a-real-value");
    await expect(dialog).toContainText(`coffer://secret/${name}`);
    await dialog.getByRole("button", { name: "Add secret" }).click();
    await expect(dialog).toBeHidden();

    // It is listed, no approval waits, and no value is on the page.
    await expect(page.getByText(name, { exact: true })).toBeVisible();
    await expect(page.getByText(/Saved, waiting for approval/)).toHaveCount(0);
    await expect(page.getByText("e2e-not-a-real-value")).toHaveCount(0);
  } finally {
    await api(`/secrets/secret/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
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

    await page.goto("/secrets");
    // One table of every secret; a row's Used by cell names what cites it.
    const row = page
      .getByRole("table")
      .getByRole("row")
      .filter({ has: page.getByRole("button", { name: `Actions for ${refOf(secret)}` }) });
    await expect(row).toBeVisible();
    await expect(row).toContainText(server);

    await row
      .getByRole("button", { name: `Actions for ${refOf(secret)}` })
      .click();
    await page.getByRole("menuitem", { name: "Delete…" }).click();
    const blocked = page.getByRole("dialog", {
      name: `${refOf(secret)} is in use`,
    });
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
    await expect(row).toBeVisible();

    // The citer opens that server's page.
    await row
      .getByRole("button", { name: new RegExp(`${refOf(secret)} is used by`) })
      .click();
    await page.getByRole("link", { name: server }).click();
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
    await page.goto("/secrets");
    const row = page
      .getByRole("table")
      .getByRole("row")
      .filter({ has: page.getByRole("button", { name: `Actions for ${refOf(name)}` }) });
    await expect(row).toBeVisible();
    // Nothing cites it: its Used by cell offers no citer to open.
    await expect(
      row.getByRole("button", { name: new RegExp(`${refOf(name)} is used by`) }),
    ).toHaveCount(0);

    await page
      .getByRole("button", { name: `Actions for ${refOf(name)}` })
      .click();
    // A browser cannot run the presence check, so Reveal names the app.
    await expect(
      page.getByRole("menuitem", { name: "Reveal in the Coffer app" }),
    ).toBeDisabled();
    await page.getByRole("menuitem", { name: "Delete…" }).click();
    const confirm = page.getByRole("dialog", {
      name: `Delete ${refOf(name)}?`,
    });
    await confirm.getByRole("button", { name: "Delete secret" }).click();
    await expect(confirm).toBeHidden();
    await expect(row).toHaveCount(0);
  } finally {
    await deleteSecret(name);
  }
});
