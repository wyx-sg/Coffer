// src/pages/CustomToolsPage.test.tsx — the Custom tools page: groups by health, one Add custom tool action,
// the group page with no tabs, the tool drawer over it, import, re-import and a hand-made request.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { makeGroup, makeTool } from "@/components/custom-tools/testFixtures";
import { CustomToolsPage } from "./CustomToolsPage";

vi.mock("@/lib/api/customTools", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/customTools")>();
  return {
    ...actual,
    customToolsApi: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      addTool: vi.fn(),
      updateTool: vi.fn(),
      removeTool: vi.fn(),
      setToolReach: vi.fn(),
      test: vi.fn(),
      readOpenApi: vi.fn(),
      previewReimport: vi.fn(),
      applyReimport: vi.fn(),
    },
  };
});
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [{ ref: "secret/billing-token", present: true }],
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

const { customToolsApi } = await import("@/lib/api/customTools");
const api = customToolsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const grafana = makeGroup({
  name: "grafana",
  health: "attention",
  health_reason: "secret_missing",
  secret_state: "missing",
  auth: {
    header: "Authorization",
    prefix: "Bearer ",
    secret: "grafana-token",
    secret_state: "missing",
  },
  tools: [makeTool({ name: "search_dashboards", path: "/search" })],
});
const deploy = makeGroup({ name: "deploy-api", health: "failing" });
const billing = makeGroup({
  name: "billing",
  source: {
    kind: "url",
    location: "https://billing.internal.example/openapi.json",
    title: null,
    version: "2.3.0",
    fetched_at: "2026-09-27T10:12:00Z",
    skipped: [],
  },
  tools: [
    makeTool({ name: "get_invoice", calls_24h: 31, failures_24h: 1 }),
    makeTool({
      name: "create_invoice",
      method: "POST",
      path: "/invoices",
      changes_data: true,
      reach_override: ["ag-cc"],
    }),
  ],
});
const status = makeGroup({ name: "status-page", enabled: false, health: "off" });
const ALL = [billing, status, grafana, deploy];

let location = "";
function LocationProbe() {
  const loc = useLocation();
  location = loc.pathname;
  return null;
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/custom-tools" element={<CustomToolsPage />} />
          <Route path="/custom-tools/:group" element={<CustomToolsPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue(ALL);
  api.get.mockImplementation(async (name: string) => ALL.find((g) => g.name === name));
});

describe("CustomToolsPage", () => {
  // scenario (web-ui, revise-web-ui-ia 7.14d): "the Custom tools page lists groups by health with one Add custom tool action"
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
    expect(within(dialog).getByRole("combobox", { name: "Group" })).toBeInTheDocument();
    const ways = within(dialog)
      .getAllByRole("radio")
      .map((r) => r.textContent ?? "");
    expect(ways.some((w) => w.includes("Import an OpenAPI spec"))).toBe(true);
    expect(ways.some((w) => w.includes("Add one request by hand"))).toBe(true);
    expect(within(dialog).queryByText(/script/i)).not.toBeInTheDocument();
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "a group's page is one page with its definition, reach, 24-hour summary and tools"
  test("a group page is one page with definition, secret, reach, 24 h line and tools; a row opens the drawer with Test", async () => {
    api.test.mockResolvedValue({
      ok: true,
      duration_ms: 180,
      url: "https://billing.internal.example/v2/invoices/7",
      status: 200,
      status_line: "200 OK",
      body: '{"id":"7"}',
      truncated: false,
      content_type: "application/json",
      error: null,
    });
    renderAt("/custom-tools/billing");
    const tools = await screen.findByRole("region", { name: /Tools · 2 of 2 on/ });
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    const definition = screen.getByRole("region", { name: "Definition" });
    expect(within(definition).getByText("billing__<tool>")).toBeInTheDocument();
    expect(
      within(definition).getByText("Authorization: Bearer ← secret billing-token"),
    ).toBeInTheDocument();
    expect(within(definition).getByTestId("scope-control")).toHaveTextContent("Every agent");
    expect(within(definition).getByRole("button", { name: "Re-import" })).toBeInTheDocument();
    expect(screen.getByText(/58 calls/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Activity" })).toBeInTheDocument();
    expect(within(tools).getByText("GET /invoices/{id}")).toBeInTheDocument();
    expect(within(tools).getByText("Override")).toBeInTheDocument();

    fireEvent.click(within(tools).getByText("get_invoice"));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("Test")).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText("Value for id"), { target: { value: "7" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Run" }));
    expect(await within(drawer).findByText(/200 OK in 180 ms/)).toBeInTheDocument();
    expect(api.test).toHaveBeenCalledWith(
      "billing",
      expect.objectContaining({ name: "get_invoice", method: "GET" }),
      { id: "7" },
    );
    expect(location).toBe("/custom-tools/billing");
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "a tool's reach override is set from its drawer"
  test("saving a tool with a reach override PUTs the override", async () => {
    api.updateTool.mockResolvedValue(billing);
    api.setToolReach.mockResolvedValue(billing);
    renderAt("/custom-tools/billing");
    const tools = await screen.findByRole("region", { name: /Tools/ });
    fireEvent.click(within(tools).getByText("get_invoice"));
    const drawer = await screen.findByRole("dialog");
    fireEvent.click(within(drawer).getByRole("radio", { name: "Only selected agents" }));
    fireEvent.click(within(drawer).getByRole("checkbox", { name: "codex" }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.setToolReach).toHaveBeenCalledWith("billing", "get_invoice", ["ag-cx"]),
    );
    expect(api.updateTool).toHaveBeenCalledWith(
      "billing",
      "get_invoice",
      expect.objectContaining({ name: "get_invoice" }),
    );
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "a hand-made request joins an existing group"
  test("a request made by hand joins the existing group it names", async () => {
    api.addTool.mockResolvedValue(billing);
    renderAt("/custom-tools");
    fireEvent.click(await screen.findByRole("button", { name: "Add custom tool" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.keyDown(within(dialog).getByRole("combobox", { name: "Group" }), {
      key: "ArrowDown",
    });
    fireEvent.click(await screen.findByRole("option", { name: "billing" }));
    fireEvent.click(within(dialog).getByRole("radio", { name: /Add one request by hand/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(location).toBe("/custom-tools/billing"));
    const drawer = await screen.findByRole("dialog", { name: "New request" });
    fireEvent.change(within(drawer).getByLabelText("Tool name"), {
      target: { value: "list_refunds" },
    });
    fireEvent.change(within(drawer).getByLabelText("Tool description"), {
      target: { value: "List refunds" },
    });
    const path = within(drawer).getByRole("textbox", { name: "Request" });
    fireEvent.change(path, { target: { value: "/refunds" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.addTool).toHaveBeenCalledWith(
        "billing",
        expect.objectContaining({ name: "list_refunds", method: "GET", path: "/refunds" }),
      ),
    );
    expect(api.create).not.toHaveBeenCalled();
  });
});

describe("CustomToolsPage import", () => {
  const reading = {
    title: "Billing API",
    version: "2.3.0",
    base_url: "https://billing.internal.example/v2",
    auth_header: "Authorization",
    auth_prefix: "Bearer ",
    source_kind: "url" as const,
    location: "https://billing.internal.example/openapi.json",
    warnings: [],
    operations: [
      {
        key: "GET /invoices",
        summary: null,
        tool: { name: "list_invoices", method: "GET" as const, path: "/invoices" },
      },
      {
        key: "GET /invoices/{id}",
        summary: null,
        tool: { name: "get_invoice", method: "GET" as const, path: "/invoices/{id}" },
      },
      {
        key: "POST /invoices",
        summary: null,
        tool: { name: "create_invoice", method: "POST" as const, path: "/invoices" },
      },
      {
        key: "DELETE /invoices/{id}",
        summary: null,
        tool: { name: "void_invoice", method: "DELETE" as const, path: "/invoices/{id}" },
      },
      {
        key: "GET /charges",
        summary: null,
        tool: { name: "list_charges", method: "GET" as const, path: "/charges" },
      },
    ],
  };

  // scenario (web-ui, revise-web-ui-ia 7.14d): "importing an OpenAPI spec creates a group with the chosen operations"
  test("import reads the spec, picks operations and posts only the chosen tools", async () => {
    api.readOpenApi.mockResolvedValue(reading);
    api.create.mockImplementation(async (body: { name: string }) => makeGroup({ name: body.name }));
    renderAt("/custom-tools");
    fireEvent.click(await screen.findByRole("button", { name: "Add custom tool" }));
    let dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Group name"), {
      target: { value: "invoices" },
    });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Import an OpenAPI spec/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    dialog = await screen.findByRole("dialog", { name: "Import an OpenAPI spec" });
    expect(within(dialog).getByLabelText("Group name")).toHaveValue("invoices");
    fireEvent.change(within(dialog).getByLabelText("Spec"), {
      target: { value: "https://billing.internal.example/openapi.json" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    expect(await within(dialog).findByText("Loaded · 5 operations")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Base URL")).toHaveValue(
      "https://billing.internal.example/v2",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Review tools" }));

    // GET operations start picked; untick one GET and pick one POST.
    expect(within(dialog).getByRole("checkbox", { name: "list_invoices" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "create_invoice" })).not.toBeChecked();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "list_charges" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "create_invoice" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group with 3 tools" }));

    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    const body = api.create.mock.calls[0][0] as {
      name: string;
      tools: { name: string }[];
      source: { kind: string; location: string; skipped: string[] };
      auth: unknown;
    };
    expect(body.name).toBe("invoices");
    expect(body.tools.map((tool) => tool.name).sort()).toEqual([
      "create_invoice",
      "get_invoice",
      "list_invoices",
    ]);
    expect(body.source).toMatchObject({
      kind: "url",
      location: "https://billing.internal.example/openapi.json",
    });
    expect(body.source.skipped.sort()).toEqual(["DELETE /invoices/{id}", "GET /charges"]);
    await waitFor(() => expect(location).toBe("/custom-tools/invoices"));
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "re-importing a spec previews the operations it adds and removes"
  test("re-import previews what it adds and removes and applies only on confirm", async () => {
    api.previewReimport.mockResolvedValue({
      title: "Billing API",
      version: "2.4.0",
      added: [
        {
          key: "GET /refunds",
          summary: null,
          tool: { name: "list_refunds", method: "GET", path: "/refunds" },
        },
        {
          key: "POST /refunds",
          summary: null,
          tool: { name: "create_refund", method: "POST", path: "/refunds" },
        },
      ],
      removed: ["create_invoice"],
      kept: ["get_invoice"],
      warnings: [],
    });
    api.applyReimport.mockResolvedValue(billing);
    renderAt("/custom-tools/billing");
    fireEvent.click(await screen.findByRole("button", { name: "Re-import" }));
    const dialog = await screen.findByRole("dialog", { name: "Re-import billing" });
    const preview = await within(dialog).findByTestId("reimport-preview");
    expect(within(preview).getByText("GET /refunds")).toBeInTheDocument();
    expect(within(preview).getByText("create_invoice (removed)")).toBeInTheDocument();
    expect(within(preview).getByText(/1 tool kept/)).toBeInTheDocument();
    expect(within(preview).getByRole("checkbox", { name: "Add list_refunds" })).toBeChecked();
    expect(within(preview).getByRole("checkbox", { name: "Add create_refund" })).not.toBeChecked();
    expect(api.applyReimport).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(api.applyReimport).toHaveBeenCalledWith("billing", ["GET /refunds"], undefined),
    );
  });
});
