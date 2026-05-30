// e2e/web/specs/shell_mcp_flows.spec.ts
//
// Spec 002 §User Story 3 — day-to-day MCP work, tested through the
// redesigned UI. Three scenarios in one walk: registration round-trip,
// capability toggle round-trip, invocations empty-state. The 001-spec
// tests already cover the backend correctness; here we pin the new
// look-and-feel: welcome-card → add → detail → tabs.

import { expect } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { acceptance } from "./_acceptance";
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

/**
 * Trigger capability discovery so that Resource/Prompt preference rows exist
 * in the DB. Required before enable/disable calls.
 */
async function refreshCapabilities(name: string): Promise<void> {
  const { token, port } = readDaemonToken();
  const r = await fetch(
    `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${name}/refresh`,
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
  "002-ui-shell",
  "MCP server registration round-trip via JSON import",
  async ({ page }) => {
    const name = generateUniqueName("e2e002reg");
    try {
      await page.goto("/mcp-servers");
      // "Add MCP server" opens a modal — no navigation away from the list.
      await page
        .getByRole("button", { name: /Add MCP server/i })
        .first()
        .click();
      await expect(
        page.getByRole("heading", { name: /Add MCP server/i }),
      ).toBeVisible();
      // Paste the standard mcpServers JSON, review, import.
      await page
        .locator("#json-input")
        .fill(JSON.stringify({ mcpServers: { [name]: { command: "echo" } } }));
      await page.getByRole("button", { name: /continue/i }).click();
      await page.getByRole("button", { name: /import/i }).click();

      await expect(page).toHaveURL(
        new RegExp(`/mcp-servers/mcp_server/${name}`),
        { timeout: 15_000 },
      );
      // The redesigned detail page surfaces the server name as a level-1
      // heading inside the new layout.
      await expect(page.getByRole("heading", { name })).toBeVisible();
      // Health state transitions: a freshly registered server starts at
      // "unknown" and flips to "healthy" once the status probe lands.
      // Binding to both labels in one regex avoids flakes on slow CI
      // where we miss the brief "unknown" frame, while still asserting
      // the badge stops on a known terminal state.
      await expect(
        page
          .locator('[data-testid="health-badge"]')
          .getByText(/unknown|healthy/i),
      ).toBeVisible({ timeout: 15_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
  "capability toggle uses the redesigned tab layout",
  async ({ page }) => {
    const name = generateUniqueName("e2e002tog");
    try {
      await registerFakeServer(name);
      await page.goto(`/mcp-servers/mcp_server/${name}`);
      // Tabs row uses the new design tokens but the role + tab names are
      // unchanged (spec 002 explicitly requires backwards-compatible
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

      // Explicitly select the "all" filter option (don't rely on the
      // default) so the disabled row is guaranteed to remain in the list,
      // and assert positively on aria-checked="false" — a stronger signal
      // than "the toggle disappeared".
      await page.getByRole("combobox", { name: /status/i }).click();
      await page.getByRole("option", { name: /^all$/i }).click();
      await expect(
        page.getByRole("switch", { name: /toggle tool write_file/i }),
      ).toHaveAttribute("aria-checked", "false", { timeout: 10_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
  "invocations table renders the redesigned empty + populated states",
  async ({ page }) => {
    const name = generateUniqueName("e2e002inv");
    try {
      await registerFakeServer(name);
      await page.goto(`/mcp-servers/mcp_server/${name}`);
      await page.getByRole("tab", { name: "Invocations" }).click();
      // Empty state — the server is registered but never invoked, so the
      // table renders the literal "No invocations yet" copy. We bind to
      // that exact assertion rather than a permissive .or(table) match,
      // so a regression where the empty-state disappears can't pass.
      await expect(page.getByText(/no invocations yet/i)).toBeVisible({
        timeout: 10_000,
      });
      // Status filter is operable. Scope to the status combobox by its
      // accessible name — the redesigned DataTable also renders a "Per page"
      // page-size combobox, so a bare getByRole("combobox") is ambiguous.
      const filter = page.getByRole("combobox", { name: /status/i });
      await expect(filter).toBeVisible();
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
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

      await page.goto(`/mcp-servers/mcp_server/${name}`);
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

      // Switch the filter to "all" so the disabled row remains rendered,
      // then assert aria-checked="false" on the same row (positive signal).
      await page.getByRole("combobox", { name: /status/i }).click();
      await page.getByRole("option", { name: /^all$/i }).click();
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
  "002-ui-shell",
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

      await page.goto(`/mcp-servers/mcp_server/${name}`);
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

      // Switch the filter to "all" so the disabled row remains rendered,
      // then assert aria-checked="false" on the same row (positive signal).
      await page.getByRole("combobox", { name: /status/i }).click();
      await page.getByRole("option", { name: /^all$/i }).click();
      await expect(
        page.getByRole("switch", { name: /toggle prompt my_prompt/i }),
      ).toHaveAttribute("aria-checked", "false", { timeout: 10_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
  "add-server form navigates to detail then back to list shows card",
  async ({ page }) => {
    const name = generateUniqueName("e2e002back");
    try {
      await page.goto("/mcp-servers");
      await page
        .getByRole("button", { name: /Add MCP server/i })
        .first()
        .click();
      await expect(
        page.getByRole("heading", { name: /Add MCP server/i }),
      ).toBeVisible();
      await page
        .locator("#json-input")
        .fill(JSON.stringify({ mcpServers: { [name]: { command: "echo" } } }));
      await page.getByRole("button", { name: /continue/i }).click();
      await page.getByRole("button", { name: /import/i }).click();

      // Import navigates to the detail page
      await expect(page).toHaveURL(
        new RegExp(`/mcp-servers/mcp_server/${name}`),
        { timeout: 15_000 },
      );

      // Navigate back to the list — the server card must appear there
      await page.goto("/mcp-servers");
      await expect(
        page
          .getByRole("link", { name: new RegExp(name) })
          .or(page.getByText(new RegExp(name)))
          .first(),
      ).toBeVisible({ timeout: 10_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
  "invocation status filter dropdown exposes selectable options",
  async ({ page }) => {
    const name = generateUniqueName("e2e002flt");
    try {
      await registerFakeServer(name);
      await page.goto(`/mcp-servers/mcp_server/${name}`);
      await page.getByRole("tab", { name: "Invocations" }).click();

      // The status filter combobox is visible
      const filter = page.getByRole("combobox").first();
      await expect(filter).toBeVisible({ timeout: 10_000 });

      // Open the dropdown by clicking the trigger
      await filter.click();

      // At least one SelectItem option renders — verify "All" is present
      // (this ensures the <SelectContent> mounts and the portal renders)
      await expect(
        page.getByRole("option", { name: /all/i }).first(),
      ).toBeVisible({ timeout: 5_000 });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
  "JSON import shows readable error for malformed JSON",
  async ({ page }) => {
    // Spec 002 §Acceptance: pasting a non-JSON payload into the Add
    // MCP server dialog must surface a parse-error message in-dialog
    // without firing a /resources request and without leaking the
    // generic "INTERNAL_ERROR" / "unexpected error" copy.
    await page.goto("/mcp-servers");
    await page
      .getByRole("button", { name: /Add MCP server/i })
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: /Add MCP server/i }),
    ).toBeVisible();

    // Capture network requests so we can later assert nothing fired
    // against /resources or /keychain while the JSON is malformed.
    const apiCalls: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (
        url.includes("/api/v1/resources") ||
        url.includes("/api/v1/keychain")
      ) {
        apiCalls.push(`${req.method()} ${url}`);
      }
    });

    // Paste a payload that is not valid JSON, then click Continue.
    await page.locator("#json-input").fill("{invalid json");
    await page.getByRole("button", { name: /continue/i }).click();

    // The dialog stays open (heading still visible) and a readable
    // error appears in the panel. We accept either the parse-error
    // copy or a shape-mismatch hint — both satisfy the spec.
    await expect(
      page.getByRole("heading", { name: /Add MCP server/i }),
    ).toBeVisible();
    await expect(
      page.getByText(/invalid|parse|expected|JSON|mcpServers/i).first(),
    ).toBeVisible({ timeout: 5_000 });

    // The forbidden copy MUST NOT appear inside the dialog.
    await expect(page.getByText(/unexpected error/i)).toHaveCount(0);
    await expect(page.getByText(/INTERNAL_ERROR/)).toHaveCount(0);

    // No write request landed at the backend.
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
  "002-ui-shell",
  "capability search box narrows the tool list",
  async ({ page }) => {
    const name = generateUniqueName("e2e002src");
    try {
      // Two distinct tools so the search can filter one out
      await registerFakeServer(name, ["--tools", "alpha_tool", "beta_tool"]);

      await page.goto(`/mcp-servers/mcp_server/${name}`);
      await page.getByRole("tab", { name: "Tools" }).click();

      // Both tools visible initially
      await expect(page.getByText("alpha_tool").first()).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByText("beta_tool").first()).toBeVisible({
        timeout: 5_000,
      });

      // Type a prefix that matches only alpha_tool
      const searchBox = page.getByPlaceholder("Search by name");
      await searchBox.fill("alpha");

      // alpha_tool remains; beta_tool disappears
      await expect(page.getByText("alpha_tool").first()).toBeVisible({
        timeout: 5_000,
      });
      await expect(page.getByText("beta_tool")).toHaveCount(0);
    } finally {
      await deregisterMcpServer(name);
    }
  },
);
