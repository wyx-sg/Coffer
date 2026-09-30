// src/pages/CustomToolsImport.test.tsx — the Custom tools page's OpenAPI import (spec and operations →
// review, only ticked operations become tools) and Re-import (the change list before Apply).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { api, billing, location, renderAt, resetCustomToolMocks } from "./customToolsTestHarness";
import { makeGroup } from "@/components/custom-tools/testFixtures";

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
vi.mock("@/lib/api/credentials", () => ({
  credentialsApi: {
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

const op = (key: string, name: string, tag: string) => {
  const [method, path] = key.split(" ") as ["GET" | "POST" | "DELETE", string];
  return { key, summary: null, tag, tool: { name, method, path } };
};

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
    op("GET /invoices", "list_invoices", "Invoices"),
    op("GET /invoices/{id}", "get_invoice", "Invoices"),
    op("POST /invoices", "create_invoice", "Invoices"),
    op("DELETE /invoices/{id}", "void_invoice", "Invoices"),
    op("GET /charges", "list_charges", "Charges"),
  ],
};

describe("CustomToolsPage import", () => {
  // scenario (web-ui, revise-web-ui-ia 7.14d): "importing an OpenAPI spec creates a group with the chosen operations"
  test("import reads the spec, ticks operations by tag and creates only the ticked ones", async () => {
    api.readOpenApi.mockResolvedValue(reading);
    api.create.mockImplementation(async (body: { name: string }) => makeGroup({ name: body.name }));
    renderAt("/custom-tools");
    fireEvent.click(await screen.findByRole("button", { name: "Add custom tool" }));
    let dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /New group/ }));
    expect(within(dialog).getByRole("radio", { name: /Import an OpenAPI spec/ })).toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    dialog = await screen.findByRole("dialog", { name: "Import an OpenAPI spec" });
    fireEvent.change(within(dialog).getByLabelText(/Group name/), {
      target: { value: "invoices" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Spec/), {
      target: { value: "https://billing.internal.example/openapi.json" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    expect(
      await within(dialog).findByText(/Loaded · 5 operations · Billing API 2.3.0/),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Invoices · 2 of 4")).toBeInTheDocument();
    expect(within(dialog).getByText("Charges · 1 of 1")).toBeInTheDocument();

    // Reads start ticked, writes do not; untick one read and tick one write.
    expect(within(dialog).getByRole("checkbox", { name: "list_invoices" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "create_invoice" })).not.toBeChecked();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "list_charges" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "create_invoice" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 3 tools" }));

    const skipped = await within(dialog).findByRole("region", { name: "Skipped · 2" });
    expect(within(skipped).getByText("void_invoice")).toBeInTheDocument();
    expect(
      within(within(dialog).getByRole("region", { name: "3 tools" })).getByText("create_invoice"),
    ).toBeInTheDocument();
    expect(api.create).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group with 3 tools" }));

    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    const body = api.create.mock.calls[0][0] as {
      name: string;
      base_url: string;
      tools: { name: string }[];
      source: { kind: string; location: string; skipped: string[] };
    };
    expect(body.name).toBe("invoices");
    expect(body.base_url).toBe("https://billing.internal.example/v2");
    expect(body.tools.map((tool) => tool.name).sort()).toEqual([
      "create_invoice",
      "get_invoice",
      "list_invoices",
    ]);
    expect(body.source).toMatchObject({ kind: "url", location: reading.location });
    expect(body.source.skipped.sort()).toEqual(["DELETE /invoices/{id}", "GET /charges"]);
    await waitFor(() => expect(location()).toBe("/custom-tools/invoices"));
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "re-importing a spec previews the operations it adds and removes"
  test("re-import lists the changes first and applies reads only on Apply", async () => {
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
      changed: [
        {
          name: "get_invoice",
          method: "GET",
          path: "/invoices/{id}",
          new_required: ["currency"],
          request_changed: false,
        },
      ],
      warnings: [],
    });
    api.applyReimport.mockResolvedValue(billing);
    renderAt("/custom-tools/billing");
    fireEvent.click(await screen.findByRole("button", { name: "Re-import" }));
    const dialog = await screen.findByRole("dialog", { name: "Re-import billing" });
    const preview = await within(dialog).findByTestId("reimport-preview");
    expect(within(preview).getByText("4 changes · Billing API 2.3.0 → 2.4.0")).toBeInTheDocument();
    expect(within(preview).getByText("Reads data — becomes a tool, on")).toBeInTheDocument();
    expect(within(preview).getByText("Changes data — listed but not ticked")).toBeInTheDocument();
    expect(within(preview).getByText("New required argument currency")).toBeInTheDocument();
    expect(within(preview).getByText("Gone from the spec — agents lose it")).toBeInTheDocument();
    expect(within(preview).getByText(/0 tools are unchanged/)).toBeInTheDocument();
    expect(api.applyReimport).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Apply 4 changes" }));
    await waitFor(() =>
      expect(api.applyReimport).toHaveBeenCalledWith("billing", ["GET /refunds"], undefined),
    );
  });
});
