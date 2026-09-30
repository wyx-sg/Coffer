// src/pages/CustomToolsPage.test.tsx — the Custom tools page: groups by health, one Add custom tool action,
// the group page with no tabs, the tool drawer over it, and a hand-made request into an existing or a
// new group (import and re-import: CustomToolsImport.test.tsx).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { api, billing, location, renderAt, resetCustomToolMocks } from "./customToolsTestHarness";

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
      "setToolReach",
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
    list: vi.fn(async () => ({ refs: [{ ref: "secret/billing-token", present: true }] })),
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
  // scenario (web-ui, revise-web-ui-ia 7.14d): "the custom tools page lists groups by health"
  test("lists groups by health, failing first, under one Add custom tool action with no script type", async () => {
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

  // scenario (web-ui, revise-web-ui-ia): "the custom tools page with no group shows the first-run panel"
  test("with no group the page is the first-run panel: no list, Add custom tool in header and body", async () => {
    api.list.mockResolvedValue([]);
    renderAt("/custom-tools");
    expect(await screen.findByText("Turn any HTTP API into tools")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Filter groups")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add custom tool" })).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /Add one request by hand/ }));
    expect(await screen.findByRole("dialog", { name: "New group" })).toBeInTheDocument();
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "a group's page is one page with a tool drawer"
  test("a group page is one page with definition, secret, reach, 24 h line and tools; a row opens the drawer with Test", async () => {
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
    const tools = await screen.findByRole("region", { name: /Tools · 2 of 2 on/ });
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    const definition = screen.getByRole("region", { name: "Definition" });
    expect(within(definition).getByText("billing__<tool>")).toBeInTheDocument();
    expect(within(definition).getByText("Authorization: Bearer")).toBeInTheDocument();
    expect(within(definition).getByText("billing-token")).toBeInTheDocument();
    expect(within(definition).getByTestId("scope-control")).toHaveTextContent("Every agent");
    expect(within(definition).getByRole("button", { name: "Re-import" })).toBeInTheDocument();
    expect(screen.getByText(/58 calls/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Activity" })).toBeInTheDocument();
    expect(within(tools).getByText("GET /invoices/{id}")).toBeInTheDocument();
    expect(within(tools).getByText("Override")).toBeInTheDocument();

    fireEvent.click(within(tools).getByText("get_invoice"));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByRole("region", { name: "Test" })).toBeInTheDocument();
    expect(within(drawer).getByText(/Not run yet/)).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText("Value for id"), { target: { value: "7" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Run" }));
    expect(await within(drawer).findByText(/200 OK in 180 ms/)).toBeInTheDocument();
    expect(api.test).toHaveBeenCalledWith(
      "billing",
      expect.objectContaining({ name: "get_invoice", method: "GET" }),
      { id: "7" },
    );
    expect(within(drawer).getByText(/Runs once with billing-token/)).toBeInTheDocument();
    expect(location()).toBe("/custom-tools/billing");
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "a tool's reach override narrows one tool"
  test("saving a tool with a reach override PUTs the override", async () => {
    api.updateTool.mockResolvedValue(billing);
    api.setToolReach.mockResolvedValue(billing);
    renderAt("/custom-tools/billing");
    const tools = await screen.findByRole("region", { name: /Tools/ });
    fireEvent.click(within(tools).getByText("get_invoice"));
    const drawer = await screen.findByRole("dialog");
    fireEvent.click(within(drawer).getByRole("button", { name: "Only for this tool" }));
    // Narrowing starts from what the group gives (every agent); the panel's
    // checklist is covered by DraftReachField.test.tsx.
    expect(within(drawer).getByRole("button", { name: "2 of 2 agents" })).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.setToolReach).toHaveBeenCalledWith("billing", "get_invoice", ["ag-cc", "ag-cx"]),
    );
    expect(api.updateTool).toHaveBeenCalledWith(
      "billing",
      "get_invoice",
      expect.objectContaining({ name: "get_invoice" }),
    );
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "a hand-made request joins an existing group"
  test("a request made by hand joins the existing group it names, and no import is offered there", async () => {
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

  // scenario (web-ui, revise-web-ui-ia): "a new group made by hand is saved with its first request"
  test("a new group made by hand is saved only with its first request, tested without the secret", async () => {
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
