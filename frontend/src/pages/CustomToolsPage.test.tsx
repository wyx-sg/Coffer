// src/pages/CustomToolsPage.test.tsx — the Custom tools page: groups by health, one Add custom tool action,
// the group page's Overview · Tools tabs (exposure included), the tool drawer over it, and a hand-made request into an existing or a
// new group (import and re-import: CustomToolsImport.test.tsx).
import { beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { makeGroup, makeTool } from "@/components/custom-tools/testFixtures";
import { resourcesApi } from "@/lib/api/resources";
import { acceptance } from "@/test/acceptance";
import {
  api,
  billing,
  location,
  mcp,
  renderAt,
  resetCustomToolMocks,
} from "./customToolsTestHarness";

vi.mock("@/lib/api/mcpServers", () => ({
  mcpServersApi: Object.fromEntries(
    ["summary", "tiering", "setToolExposure"].map((name) => [name, vi.fn()]),
  ),
}));
vi.mock("@/lib/api/customTools", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/customTools")>()),
  customToolsApi: Object.fromEntries(
    [
      "list",
      "get",
      "create",
      "update",
      "remove",
      "addTool",
      "updateTool",
      "removeTool",
      "test",
      "testUnsaved",
      "readOpenApi",
      "previewReimport",
      "applyReimport",
    ].map((name) => [name, vi.fn()]),
  ),
}));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: "secret/billing-token",
          present: true,
          locked: false,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
  },
}));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({
    data: [
      { uid: "ag-cc", name: "claude-code", type: "claude_code", state: "installed" },
      { uid: "ag-cx", name: "codex", type: "codex", state: "installed" },
    ],
  })),
}));

beforeEach(resetCustomToolMocks);

describe("CustomToolsPage", () => {
  acceptance("web-ui", "the custom tools page lists groups by health", async () => {
    renderAt("/custom-tools");
    const attention = await screen.findByRole("region", { name: "Needs attention" });
    const names = within(attention)
      .getAllByRole("button", { current: false })
      .map((b) => b.textContent ?? "")
      .filter((text) => /deploy-api|grafana/.test(text));
    expect(names[0]).toContain("deploy-api");
    expect(names[1]).toContain("grafana");
    expect(within(attention).getByText("Secret missing · grafana-token")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Healthy" })).getByText("billing"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Off" })).getByText("status-page"),
    ).toBeInTheDocument();

    // Only the page header holds Add; the Nothing selected pane has none.
    const adds = screen.getAllByRole("button", { name: "Add custom tool" });
    expect(adds).toHaveLength(1);
    fireEvent.click(adds[0]);

    const dialog = await screen.findByRole("dialog");
    const putItIn = within(dialog).getByRole("radiogroup", { name: "Put it in" });
    expect(within(putItIn).getByRole("radio", { name: /billing/ })).toBeInTheDocument();
    fireEvent.click(within(putItIn).getByRole("radio", { name: /New group/ }));
    const ways = within(dialog).getByRole("radiogroup", { name: "How to add it" });
    expect(within(ways).getByRole("radio", { name: /Import an OpenAPI spec/ })).toBeInTheDocument();
    expect(
      within(ways).getByRole("radio", { name: /Add one request by hand/ }),
    ).toBeInTheDocument();
    expect(within(dialog).queryByText(/script/i)).not.toBeInTheDocument();
  });

  acceptance("web-ui", "ticking a group puts the selection bar at the top", async () => {
    renderAt("/custom-tools");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select row: billing" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select row: grafana" }));
    const bar = screen.getByRole("region", { name: "Selected custom tool groups" });
    expect(within(bar).getByText("2 of 4 selected")).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: /Reach/ })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Clear selection" })).toBeInTheDocument();

    fireEvent.click(within(bar).getByRole("button", { name: /Reach/ }));
    fireEvent.click(await screen.findByRole("radio", { name: /Off/ }));
    fireEvent.click(screen.getByRole("button", { name: /Apply/ }));
    await waitFor(() => expect(resourcesApi.disable).toHaveBeenCalledTimes(2));
    expect(resourcesApi.disable).toHaveBeenCalledWith("uid-billing");
    expect(resourcesApi.disable).toHaveBeenCalledWith("uid-grafana");
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Selected custom tool groups" })).toBeNull(),
    );
  });

  test("bulk Delete removes each ticked group and leaves a deleted group's page", async () => {
    api.remove.mockResolvedValue(undefined);
    renderAt("/custom-tools/billing");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select row: billing" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select row: status-page" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete 2 groups?")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledTimes(2));
    expect(api.remove).toHaveBeenCalledWith("billing");
    expect(api.remove).toHaveBeenCalledWith("status-page");
    await waitFor(() => expect(location()).toBe("/custom-tools"));
  });

  acceptance("web-ui", "the list narrows to one agent", async () => {
    api.list.mockResolvedValue([
      makeGroup({ name: "only-claude", scope: ["ag-cc"] }),
      makeGroup({ name: "everyone", scope: null }),
    ]);
    renderAt("/custom-tools?agent=ag-cx");
    expect(await screen.findByText("everyone")).toBeInTheDocument();
    expect(screen.queryByText("only-claude")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Reach" })).toHaveTextContent("Codex");
  });

  acceptance("web-ui", "the tools table has no reach column and is searched by name", async () => {
    const invoices = makeGroup({
      name: "billing",
      tools: ["list_invoices", "refund", "void_invoice"].map((name) => makeTool({ name })),
    });
    api.list.mockResolvedValue([invoices]);
    api.get.mockResolvedValue(invoices);
    renderAt("/custom-tools/billing/tools");
    const tools = await screen.findByRole("region", { name: /Tools/ });
    expect(within(tools).queryByRole("columnheader", { name: "Available to" })).toBeNull();
    expect(within(tools).queryByRole("button", { name: /Available to/ })).toBeNull();

    fireEvent.change(within(tools).getByRole("textbox", { name: "Filter tools" }), {
      target: { value: "invoice" },
    });
    const table = within(tools).getByRole("table");
    expect(within(table).getByText("list_invoices")).toBeInTheDocument();
    expect(within(table).getByText("void_invoice")).toBeInTheDocument();
    expect(within(table).queryByText("refund")).toBeNull();
    // The count still speaks for the whole group.
    expect(within(tools).getByText("3 of 3 on")).toBeInTheDocument();

    // Add request sits above the table, beside the search, and not below it.
    const add = within(tools).getByRole("button", { name: "Add request" });
    expect(add.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(tools).getAllByRole("button", { name: "Add request" })).toHaveLength(1);

    fireEvent.change(within(tools).getByRole("textbox", { name: "Filter tools" }), {
      target: { value: "zzz" },
    });
    expect(within(tools).getByText("No tool matches “zzz”")).toBeInTheDocument();
    fireEvent.click(within(tools).getByRole("button", { name: "Clear filter" }));
    expect(within(tools).getByText("refund")).toBeInTheDocument();
  });

  acceptance(
    "web-ui",
    "the custom tools page with no group shows the first-run panel",
    async () => {
      api.list.mockResolvedValue([]);
      renderAt("/custom-tools");
      expect(await screen.findByText("No custom tools yet")).toBeInTheDocument();
      expect(screen.queryByPlaceholderText("Filter groups")).not.toBeInTheDocument();
      // Only the page header's Add: the two cards are the way in.
      expect(screen.getAllByRole("button", { name: "Add custom tool" })).toHaveLength(1);
      fireEvent.click(screen.getByRole("button", { name: /Add one request by hand/ }));
      expect(await screen.findByRole("dialog", { name: "New group" })).toBeInTheDocument();
    },
  );

  acceptance("web-ui", "a group's page has Overview and Tools tabs", async () => {
    api.test.mockResolvedValue({
      ok: true,
      duration_ms: 180,
      url: "https://billing.internal.example/v2/invoices/7",
      status: 200,
      status_line: "HTTP 200 OK",
      body: '{"id":"7"}',
      truncated: false,
      content_type: "application/json",
      error: null,
      failure: null,
    });
    renderAt("/custom-tools/billing");
    // Overview, the bare address: the definition, and no tools table.
    const definition = await screen.findByRole("region", { name: "Definition" });
    expect(
      within(screen.getByRole("tablist"))
        .getAllByRole("tab")
        .map((tab) => tab.textContent),
    ).toEqual(["Overview", "Tools"]);
    expect(screen.queryByRole("region", { name: "Tools" })).not.toBeInTheDocument();
    expect(within(definition).getByText("billing__<tool>")).toBeInTheDocument();
    // The group's header reads `name ← 🔑 secret` (the secret is the whole value, no prefix).
    expect(within(definition).getByText("Authorization")).toBeInTheDocument();
    expect(within(definition).getByText("billing-token")).toBeInTheDocument();
    expect(within(definition).getByText("30 s per call")).toBeInTheDocument();
    expect(within(definition).queryByText(/Available to/)).not.toBeInTheDocument();
    expect(within(definition).getByRole("button", { name: "Re-import" })).toBeInTheDocument();
    // The header: state pill, one meta line, then Reach · Edit group · ⋯ — no "?".
    const header = screen.getByTestId("custom-tool-group-tile").closest("header") as HTMLElement;
    expect(within(header).getByText("Healthy")).toBeInTheDocument();
    expect(within(header).getByTestId("scope-control")).toHaveTextContent("All agents");
    expect(within(header).getByRole("button", { name: "Edit group" })).toBeInTheDocument();
    expect(within(header).queryByRole("button", { name: /more info/i })).not.toBeInTheDocument();
    // The header's ⋯ menu holds only Delete: Edit, Re-import and on/off are visible controls.
    fireEvent.click(screen.getByRole("button", { name: /more actions for billing/i }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Delete group…"]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.getByText(/58 calls, 2 errors in 24 h/)).toBeInTheDocument();

    // Tools: the table, the tab in the path. Radix tabs switch on mouse-down.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Tools" }));
    await waitFor(() => expect(location()).toBe("/custom-tools/billing/tools"));
    const tools = await screen.findByRole("region", { name: "Tools" });
    expect(within(tools).getByText("GET /invoices/{id}")).toBeInTheDocument();
    expect(within(tools).getByText("2 of 2 on")).toBeInTheDocument();
    // A tool has no reach of its own: the group's header carries it.
    expect(within(tools).queryByRole("button", { name: /Available to/ })).toBeNull();

    fireEvent.click(within(tools).getByText("get_invoice"));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByRole("region", { name: "Test" })).toBeInTheDocument();
    expect(within(drawer).getByText(/Not run yet/)).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText("Value for id"), { target: { value: "7" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Run" }));
    expect(await within(drawer).findByText(/200 OK · 180 ms/)).toBeInTheDocument();
    // The response sits in the viewer under the result block.
    expect(within(drawer).getByTestId("custom-tool-response")).toBeInTheDocument();
    expect(api.test).toHaveBeenCalledWith(
      "billing",
      expect.objectContaining({ name: "get_invoice", method: "GET" }),
      { id: "7" },
    );
    expect(within(drawer).getByText(/Runs once with billing-token/)).toBeInTheDocument();
    expect(location()).toBe("/custom-tools/billing/tools");
    fireEvent.click(within(drawer).getByRole("button", { name: "Cancel" }));
  });

  acceptance(
    "web-ui",
    "a group's Overview shows what it requires, its busiest tools and the last 24 hours",
    async () => {
      renderAt("/custom-tools/billing");
      // Last 24 hours: the totals, the agents that called, and View in Activity.
      const last = await screen.findByRole("region", { name: "Last 24 hours" });
      expect(await within(last).findByTestId("mcp-24h-totals")).toHaveTextContent("31");
      expect(within(last).getByRole("table", { name: "Called by" })).toBeInTheDocument();
      expect(within(last).getByRole("link", { name: "View in Activity" })).toHaveAttribute(
        "href",
        "/activity?tab=mcp&q=billing",
      );
      expect(mcp.summary).toHaveBeenCalledWith("uid-billing");
      // Requires: the secret its header cites, by the secret's own name, linked to Secrets.
      const requires = screen.getByRole("region", { name: "Requires" });
      expect(within(requires).getByText("billing-token")).toBeInTheDocument();
      expect(within(requires).getByText("Set")).toBeInTheDocument();
      expect(within(requires).getByRole("link", { name: "View in Secrets" })).toHaveAttribute(
        "href",
        "/secrets?q=billing-token",
      );
      expect(within(requires).queryByText("CLI")).toBeNull();
      // Most-called tools: read-only, busiest first, no switches.
      const top = screen.getByRole("region", { name: "Most-called tools" });
      const rows = within(top).getAllByRole("row").slice(1);
      expect(rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual([
        expect.stringContaining("get_invoice"),
        expect.stringContaining("create_invoice"),
      ]);
      expect(within(top).queryByRole("switch")).toBeNull();
    },
  );

  acceptance("web-ui", "a custom tool's exposure is set on the group's Tools tab", async () => {
    renderAt("/custom-tools/billing/tools");
    const tools = await screen.findByRole("region", { name: "Tools" });
    expect(
      await within(tools).findByRole("combobox", { name: "Exposure of get_invoice" }),
    ).toHaveTextContent("Auto · Listed");
    expect(
      within(tools).getByRole("combobox", { name: "Exposure of create_invoice" }),
    ).toHaveTextContent("Always listed");
    expect(mcp.tiering).toHaveBeenCalledWith("uid-billing");
    const trigger = within(tools).getByRole("combobox", { name: "Exposure of get_invoice" });
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.click(await screen.findByRole("option", { name: "Search only" }));
    await waitFor(() =>
      expect(mcp.setToolExposure).toHaveBeenCalledWith("uid-billing", ["get_invoice"], "search"),
    );
    // Choosing the exposure never opens the tool's drawer.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  acceptance("web-ui", "a tool's drawer has no switch, and Delete tool is outlined", async () => {
    renderAt("/custom-tools/billing/tools");
    const tools = await screen.findByRole("region", { name: /Tools/ });
    fireEvent.click(within(tools).getByText("get_invoice"));
    const drawer = await screen.findByRole("dialog");
    // The tool's own On switch is in the table, not in the drawer footer.
    expect(within(drawer).queryByLabelText("Tool on")).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/Only for this tool/)).not.toBeInTheDocument();
    // The group's header shows as what the group already adds.
    expect(within(drawer).getByText("from the group")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Delete tool" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  acceptance("web-ui", "a hand-made request joins an existing group", async () => {
    api.addTool.mockResolvedValue(billing);
    renderAt("/custom-tools");
    fireEvent.click(await screen.findByRole("button", { name: "Add custom tool" }));
    let dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /^billing/ }));
    expect(within(dialog).queryByRole("radio", { name: /Import an OpenAPI spec/ })).toBeNull();
    expect(within(dialog).getByText(/uses its base URL and secret/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    dialog = await screen.findByRole("dialog", { name: "Add a request" });
    fireEvent.change(within(dialog).getByLabelText(/Tool name/), {
      target: { value: "list_refunds" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Tool description/), {
      target: { value: "List refunds" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /Request/ }), {
      target: { value: "/refunds" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add to billing" }));
    await waitFor(() =>
      expect(api.addTool).toHaveBeenCalledWith(
        "billing",
        expect.objectContaining({ name: "list_refunds", method: "GET", path: "/refunds" }),
      ),
    );
    expect(api.create).not.toHaveBeenCalled();
    await waitFor(() => expect(location()).toBe("/custom-tools/billing"));
  });

  acceptance("web-ui", "a new group made by hand is saved with its first request", async () => {
    api.testUnsaved.mockResolvedValue({
      ok: false,
      duration_ms: 0,
      url: "https://search.internal.example/v1",
      status: null,
      status_line: null,
      body: "",
      truncated: false,
      content_type: null,
      error: "SSRF: refusing host search.internal.example",
      failure: "blocked",
    });
    api.create.mockImplementation(async (body: { name: string }) => ({
      ...billing,
      name: body.name,
    }));
    renderAt("/custom-tools");
    fireEvent.click(await screen.findByRole("button", { name: "Add custom tool" }));
    let dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /New group/ }));
    fireEvent.click(within(dialog).getByRole("radio", { name: /Add one request by hand/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    dialog = await screen.findByRole("dialog", { name: "New group" });
    fireEvent.change(within(dialog).getByLabelText(/Group name/), {
      target: { value: "search-api" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Base URL/), {
      target: { value: "https://search.internal.example/v1" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group" }));

    dialog = await screen.findByRole("dialog", { name: "Add a request" });
    expect(api.create).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByLabelText(/Tool name/), { target: { value: "find" } });
    fireEvent.change(within(dialog).getByLabelText(/Tool description/), {
      target: { value: "Find things" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /Request/ }), {
      target: { value: "/find" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Run" }));
    expect(
      await within(dialog).findByText(/isn't tested before the group is saved/),
    ).toBeInTheDocument();
    expect(api.testUnsaved).toHaveBeenCalledWith(
      expect.objectContaining({
        base_url: "https://search.internal.example/v1",
        tool: expect.objectContaining({ name: "find", path: "/find" }),
      }),
    );
    expect(api.test).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/Runs once without the secret/)).toBeInTheDocument();
    expect(api.create).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Add to search-api" }));
    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    expect(api.create.mock.calls[0][0]).toMatchObject({
      name: "search-api",
      base_url: "https://search.internal.example/v1",
      tools: [expect.objectContaining({ name: "find", path: "/find" })],
    });
    await waitFor(() => expect(location()).toBe("/custom-tools/search-api"));
  });
});
