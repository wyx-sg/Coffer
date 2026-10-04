// e2e/web/specs/shell_mcp_flows.spec.ts
//
// Spec web-ui §User Story 3 — day-to-day MCP work, tested through the
// redesigned UI: registration round-trip and capability toggle
// round-trip. The 001-spec tests already cover the backend correctness;
// here we pin the new look-and-feel: welcome-card → add → detail → tabs.

import { expect, test } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { acceptance } from "./_acceptance";
import {
  beforeEachInjectToken,
  deregisterMcpServer,
  generateUniqueName,
  readDaemonToken,
  resolveResourceUid,
} from "./_helpers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const PYTHON = path.join(REPO_ROOT, ".venv/bin/python3");
const FAKE_SERVER = path.join(
  REPO_ROOT,
  "backend/tests/fixtures/fake_mcp_server.py",
);

beforeEachInjectToken();

async function registerFakeServer(
  name: string,
  extraArgs: string[] = ["--tools", "read_file", "write_file"],
): Promise<void> {
  const { token, port } = readDaemonToken();
  const r = await fetch(`http://127.0.0.1:${port}/api/v1/resources`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    body: JSON.stringify({
      kind: "mcp_server",
      name,
      config: {
        transport: {
          type: "stdio",
          command: PYTHON,
          args: [FAKE_SERVER, "--scenario", "basic", ...extraArgs],
        },
      },
    }),
  });
  if (!r.ok) throw new Error(`register failed: ${r.status} ${await r.text()}`);
}

/** The uid of the server called ``name`` — what every route addresses. */
async function uidOf(name: string): Promise<string> {
  const uid = await resolveResourceUid("mcp_server", name);
  if (uid === null) throw new Error(`no mcp_server named ${name}`);
  return uid;
}

/**
 * Trigger capability discovery so that Resource/Prompt preference rows exist
 * in the DB. Required before enable/disable calls.
 */
async function refreshCapabilities(name: string): Promise<void> {
  const { token, port } = readDaemonToken();
  const uid = await uidOf(name);
  const r = await fetch(
    `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${uid}/refresh`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Coffer-Token": token,
        "X-Coffer-Actor": "e2e",
      },
    },
  );
  if (!r.ok) throw new Error(`refresh failed: ${r.status} ${await r.text()}`);
}

acceptance(
  "web-ui",
  "MCP server registration round-trip via JSON import",
  async ({ page }) => {
    const name = generateUniqueName("e2e002reg");
    try {
      await page.goto("/mcp-servers");
      // "Add server" opens a modal — no navigation away from the list.
      await page
        .getByRole("button", { name: /^add server$/i })
        .first()
        .click();
      await expect(
        page.getByRole("heading", { name: /Add MCP server/i }),
      ).toBeVisible();
      // Paste the standard mcpServers JSON: one server opens the prefilled form.
      await page.locator("#mcp-paste").fill(
        JSON.stringify({
          mcpServers: {
            [name]: {
              command: PYTHON,
              args: [
                FAKE_SERVER,
                "--scenario",
                "basic",
                "--tools",
                "read_file",
              ],
            },
          },
        }),
      );
      await page.getByRole("button", { name: /^continue$/i }).click();
      await expect(page.locator("#add-server-name")).toHaveValue(name);
      await page
        .getByRole("button", { name: /^add server$/i })
        .last()
        .click();

      // It lands on the new server, addressed by its fixed name.
      await expect(page).toHaveURL(new RegExp(`/mcp-servers/${name}$`), {
        timeout: 15_000,
      });
      await expect(page.getByRole("heading", { level: 1, name })).toBeVisible({
        timeout: 15_000,
      });
      // A freshly registered server reads "Not checked yet" until its first
      // test lands, then "Healthy" (the add runs one test right away).
      await expect(
        page
          .getByTestId("mcp-server-pane")
          .getByText(/^(not checked yet|healthy)$/i)
          .first(),
      ).toBeVisible({ timeout: 15_000 });
      await expect(
        page
          .getByTestId("mcp-server-pane")
          .getByText(/^healthy$/i)
          .first(),
      ).toBeVisible({ timeout: 20_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "web-ui",
  "capability toggle uses the redesigned tab layout",
  async ({ page }) => {
    const name = generateUniqueName("e2e002tog");
    try {
      await registerFakeServer(name);
      await page.goto(`/mcp-servers/${encodeURIComponent(name)}`);
      // Tabs row uses the new design tokens but the role + tab names are
      // unchanged (spec web-ui explicitly requires backwards-compatible
      // selectors here).
      await page.getByRole("tab", { name: "Tools" }).click();
      await expect(page.getByText("read_file").first()).toBeVisible({
        timeout: 15_000,
      });
      const toggle = page.getByRole("switch", {
        name: /toggle tool write_file/i,
      });
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-checked", "true");
      await toggle.click();

      // The tab has no status filter, so the disabled row stays listed;
      // assert positively on aria-checked="false" — a stronger signal than
      // "the toggle disappeared".
      await expect(
        page.getByRole("switch", { name: /toggle tool write_file/i }),
      ).toHaveAttribute("aria-checked", "false", { timeout: 10_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "web-ui",
  "resource capability toggle works via the Resources tab",
  async ({ page }) => {
    const name = generateUniqueName("e2e002res");
    try {
      // Register a fake server that exposes one resource URI.
      // Use a simple urn: URI to avoid URL-encoding issues with slashes.
      await registerFakeServer(name, [
        "--tools",
        "read_file",
        "--resources",
        "urn:test-resource",
      ]);
      // Discovery must run before the UI can toggle
      await refreshCapabilities(name);

      await page.goto(`/mcp-servers/${encodeURIComponent(name)}`);
      await page.getByRole("tab", { name: "Resources" }).click();

      // The resource row appears with its URI and is enabled by default
      await expect(page.getByText("urn:test-resource").first()).toBeVisible({
        timeout: 15_000,
      });
      const toggle = page.getByRole("switch", {
        name: /toggle resource urn:test-resource/i,
      });
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-checked", "true");

      // Disable the resource
      await toggle.click();

      // The disabled row stays listed; assert aria-checked="false" on it.
      await expect(
        page.getByRole("switch", {
          name: /toggle resource urn:test-resource/i,
        }),
      ).toHaveAttribute("aria-checked", "false", { timeout: 10_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "web-ui",
  "prompt capability toggle works via the Prompts tab",
  async ({ page }) => {
    const name = generateUniqueName("e2e002prm");
    try {
      // Register a fake server that exposes one prompt
      await registerFakeServer(name, [
        "--tools",
        "read_file",
        "--prompts",
        "my_prompt",
      ]);
      // Discovery must run before the UI can toggle
      await refreshCapabilities(name);

      await page.goto(`/mcp-servers/${encodeURIComponent(name)}`);
      await page.getByRole("tab", { name: "Prompts" }).click();

      // The prompt row appears and is enabled by default
      await expect(page.getByText("my_prompt").first()).toBeVisible({
        timeout: 15_000,
      });
      const toggle = page.getByRole("switch", {
        name: /toggle prompt my_prompt/i,
      });
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-checked", "true");

      // Disable the prompt
      await toggle.click();

      // The disabled row stays listed; assert aria-checked="false" on it.
      await expect(
        page.getByRole("switch", { name: /toggle prompt my_prompt/i }),
      ).toHaveAttribute("aria-checked", "false", { timeout: 10_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "web-ui",
  "add-server form navigates to detail then back to list shows card",
  async ({ page }) => {
    const name = generateUniqueName("e2e002back");
    try {
      await page.goto("/mcp-servers");
      await page
        .getByRole("button", { name: /^add server$/i })
        .first()
        .click();
      await expect(
        page.getByRole("heading", { name: /Add MCP server/i }),
      ).toBeVisible();
      // No paste: choose the type by hand and fill the form.
      await page.getByRole("button", { name: /command \(stdio\)/i }).click();
      await page.locator("#add-server-name").fill(name);
      await page.locator("#add-server-command").fill("echo");
      await page
        .getByRole("button", { name: /^add server$/i })
        .last()
        .click();

      await expect(page).toHaveURL(new RegExp(`/mcp-servers/${name}$`), {
        timeout: 15_000,
      });
      await expect(page.getByRole("heading", { level: 1, name })).toBeVisible({
        timeout: 15_000,
      });

      // Back on the list the server is a row.
      await page.goto("/mcp-servers");
      await expect(
        page.getByRole("link", { name: new RegExp(name) }).first(),
      ).toBeVisible({ timeout: 10_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "web-ui",
  "JSON import shows readable error for malformed JSON",
  async ({ page }) => {
    // Pasting a non-JSON payload into the Add server dialog surfaces a
    // readable message in the dialog without firing a request and without
    // the generic "INTERNAL_ERROR" / "unexpected error" copy.
    await page.goto("/mcp-servers");
    await page
      .getByRole("button", { name: /^add server$/i })
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: /Add MCP server/i }),
    ).toBeVisible();

    const apiCalls: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (
        url.includes("/api/v1/resources") ||
        url.includes("/api/v1/secrets")
      ) {
        apiCalls.push(`${req.method()} ${url}`);
      }
    });

    // The box reads as the user types: a readable parse error appears at
    // once and Continue stays disabled, so nothing can reach the daemon.
    await page.locator("#mcp-paste").fill('{"mcpServers": {"x": }');
    await expect(page.locator("#mcp-paste-result")).toContainText(
      /not valid json|json/i,
      { timeout: 5_000 },
    );
    await expect(
      page.getByRole("button", { name: /^continue$/i }),
    ).toBeDisabled();

    await expect(page.getByText(/unexpected error/i)).toHaveCount(0);
    await expect(page.getByText(/INTERNAL_ERROR/)).toHaveCount(0);
    await expect(page.getByText(/internal error/i)).toHaveCount(0);

    expect(
      apiCalls.filter(
        (c) =>
          c.startsWith("POST") ||
          c.startsWith("PATCH") ||
          c.startsWith("DELETE"),
      ),
    ).toHaveLength(0);
  },
);

acceptance(
  "web-ui",
  "capability search box narrows the tool list",
  async ({ page }) => {
    const name = generateUniqueName("e2e002src");
    try {
      // Two distinct tools so the search can filter one out
      await registerFakeServer(name, ["--tools", "alpha_tool", "beta_tool"]);

      await page.goto(`/mcp-servers/${encodeURIComponent(name)}`);
      await page.getByRole("tab", { name: "Tools" }).click();

      // Both tools visible initially
      await expect(page.getByText("alpha_tool").first()).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByText("beta_tool").first()).toBeVisible({
        timeout: 5_000,
      });

      // Type a prefix that matches only alpha_tool
      const searchBox = page.getByPlaceholder("Search tools");
      await searchBox.fill("alpha");

      // alpha_tool remains; beta_tool disappears
      await expect(page.getByText("alpha_tool").first()).toBeVisible({
        timeout: 5_000,
      });
      // Exact: the server's header names its command line, which carries both.
      await expect(page.getByText("beta_tool", { exact: true })).toHaveCount(0);
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

// --- the paste box's other forms (AddMcpServerDialog.test.tsx carries the
// scenarios' acceptance markers) ----------------------------------------------

test("pasting JSON with three servers opens the review and adds all three", async ({
  page,
}) => {
  const names = ["a", "b", "c"].map((x) => generateUniqueName(`e2e3${x}`));
  try {
    await page.goto("/mcp-servers");
    await page
      .getByRole("button", { name: /^add server$/i })
      .first()
      .click();
    const servers = Object.fromEntries(
      names.map((n) => [
        n,
        {
          command: PYTHON,
          args: [FAKE_SERVER, "--scenario", "basic", "--tools", "t"],
        },
      ]),
    );
    await page
      .locator("#mcp-paste")
      .fill(JSON.stringify({ mcpServers: servers }));
    await expect(page.locator("#mcp-paste-result")).toContainText(
      /found 3 servers/i,
    );
    await page.getByRole("button", { name: /review 3 servers/i }).click();
    await expect(
      page.getByRole("heading", { name: /review before adding/i }),
    ).toBeVisible();
    await page.getByRole("button", { name: /add 3 servers/i }).click();
    await expect(
      page.getByRole("heading", { name: /review before adding/i }),
    ).toHaveCount(0, {
      timeout: 15_000,
    });
    for (const n of names) {
      await expect(
        page.getByRole("link", { name: new RegExp(n) }).first(),
      ).toBeVisible({
        timeout: 10_000,
      });
      expect(await resolveResourceUid("mcp_server", n)).not.toBeNull();
    }
  } finally {
    for (const n of names) await deregisterMcpServer(n);
  }
});

test("pasting a command line prefills a stdio server", async ({ page }) => {
  await page.goto("/mcp-servers");
  await page
    .getByRole("button", { name: /^add server$/i })
    .first()
    .click();
  await page
    .locator("#mcp-paste")
    .fill(
      "claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github",
    );
  await expect(page.locator("#mcp-paste-result")).toContainText(
    /command · stdio/i,
  );
  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.locator("#add-server-name")).toHaveValue("github");
  await expect(page.locator("#add-server-command")).toHaveValue("npx");
  await expect(page.locator("#add-server-args")).toHaveValue(
    "-y @modelcontextprotocol/server-github",
  );
  // A pasted value is not kept in the config: the variable becomes a new
  // secret, saved when the server is added.
  await expect(
    page.getByRole("button", { name: "GITHUB_TOKEN: secret github_token" }),
  ).toContainText("New · saved on Add");
  // Nothing was added: close without saving.
  await page.keyboard.press("Escape");
});

test("pasting a URL prefills a Streamable HTTP server", async ({ page }) => {
  await page.goto("/mcp-servers");
  await page
    .getByRole("button", { name: /^add server$/i })
    .first()
    .click();
  await page.locator("#mcp-paste").fill("https://mcp.example.com/mcp");
  await expect(page.locator("#mcp-paste-result")).toContainText(
    /url · streamable http/i,
  );
  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.locator("#add-server-url")).toHaveValue(
    "https://mcp.example.com/mcp",
  );
  await expect(page.locator("#add-server-name")).toHaveValue("example");
  await page.keyboard.press("Escape");
});
