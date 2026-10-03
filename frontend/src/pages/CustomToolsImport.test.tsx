// src/pages/CustomToolsImport.test.tsx — the Custom tools page's OpenAPI import (spec and operations →
// review, only ticked operations become tools) and Re-import (the change list before Apply).
import { beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
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
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: "secret/billing-token",
          present: true,
          locked: false,
          bindings: [],
          cited_by: [],
          mentioned_by_skills: [],
        },
      ],
    })),
    set: vi.fn(),
    pendingApprovals: vi.fn(async () => ({ approvals: [] })),
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
  const source = {
    start_line: 212,
    end_line: 214,
    text: `"${path}": {\n  "operationId": "${name}"\n}`,
  };
  return { key, summary: null, tag, source, tool: { name, method, path } };
};

const reading = {
  title: "Billing API",
  version: "2.3.0",
  base_url: "https://billing.internal.example/v2",
  auth_header: "Authorization",
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
  acceptance(
    "web-ui",
    "importing an OpenAPI spec creates a group with the chosen operations",
    async () => {
      api.readOpenApi.mockResolvedValue(reading);
      api.create.mockImplementation(async (body: { name: string }) =>
        makeGroup({ name: body.name }),
      );
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
      // The spec's security scheme pre-fills one Authorization row, with no value yet.
      expect(within(dialog).getByLabelText("Headers name")).toHaveValue("Authorization");
      fireEvent.change(within(dialog).getByLabelText("Value of Authorization"), {
        target: { value: "Bearer abc" },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Review 3 tools" }));

      // The review: the group and its tools on the left, the chosen operation's spec text on the right.
      dialog = await screen.findByRole("dialog", { name: "Import an OpenAPI spec" });
      expect(within(dialog).getByText("invoices__list_invoices")).toBeInTheDocument();
      expect(within(dialog).getByText(/"operationId": "list_invoices"/)).toBeInTheDocument();
      expect(within(dialog).getByText("212")).toBeInTheDocument();
      fireEvent.click(within(dialog).getByRole("button", { name: /void_invoice/ }));
      expect(within(dialog).getByText(/"operationId": "void_invoice"/)).toBeInTheDocument();
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
        headers: { name: string; value?: string }[];
        agents: string[] | null;
        tools: { name: string }[];
        source: { kind: string; location: string; skipped: string[] };
      };
      expect(body.name).toBe("invoices");
      expect(body.base_url).toBe("https://billing.internal.example/v2");
      expect(body.headers).toEqual([{ name: "Authorization", value: "Bearer abc" }]);
      expect(body.agents).toBeNull();
      expect(body.tools.map((tool) => tool.name).sort()).toEqual([
        "create_invoice",
        "get_invoice",
        "list_invoices",
      ]);
      expect(body.source).toMatchObject({ kind: "url", location: reading.location });
      expect(body.source.skipped.sort()).toEqual(["DELETE /invoices/{id}", "GET /charges"]);
      await waitFor(() => expect(location()).toBe("/custom-tools/invoices"));
    },
  );

  acceptance(
    "web-ui",
    "an unreachable spec URL names the reason and keeps Review tools off",
    async () => {
      api.readOpenApi.mockRejectedValue(
        new ApiError("OPENAPI_UNREACHABLE", "could not reach", {
          reason: "refused",
          handoff: { prompt: "Find out why" },
        }),
      );
      renderAt("/custom-tools");
      fireEvent.click(await screen.findByRole("button", { name: "Add custom tool" }));
      let dialog = await screen.findByRole("dialog");
      fireEvent.click(within(dialog).getByRole("radio", { name: /New group/ }));
      fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
      dialog = await screen.findByRole("dialog", { name: "Import an OpenAPI spec" });
      expect(within(dialog).getByText("Import an OpenAPI spec · new group")).toBeInTheDocument();
      const url = within(dialog).getByLabelText(/Spec/);
      fireEvent.change(url, { target: { value: "https://billing.internal.example/openapi.yaml" } });
      fireEvent.click(within(dialog).getByRole("button", { name: "Load" }));
      expect(
        await within(dialog).findByText(
          "Couldn't reach billing.internal.example: connection refused. Check the URL, your network, VPN or proxy.",
        ),
      ).toBeInTheDocument();
      expect(url).toHaveAttribute("aria-invalid", "true");
      expect(within(dialog).getByRole("button", { name: "Retry" })).toBeInTheDocument();
      expect(
        within(dialog).getByRole("button", { name: /Ask an agent|Copy prompt/ }),
      ).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Review tools" })).toBeDisabled();
    },
  );

  acceptance(
    "web-ui",
    "a spec that does not parse shows the lines around the failure",
    async () => {
      api.readOpenApi.mockRejectedValue(
        new ApiError("OPENAPI_UNREADABLE", "a mapping value isn't allowed here", {
          line: 3,
          column: 5,
        }),
      );
      renderAt("/custom-tools");
      fireEvent.click(await screen.findByRole("button", { name: "Add custom tool" }));
      let dialog = await screen.findByRole("dialog");
      fireEvent.click(within(dialog).getByRole("radio", { name: /New group/ }));
      fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
      dialog = await screen.findByRole("dialog", { name: "Import an OpenAPI spec" });
      fireEvent.click(within(dialog).getByRole("radio", { name: "File" }));
      const text = "openapi: 3.0.0\npaths:\n  /a: b: c\n  /d: {}";
      const file = new File([text], "openapi.yaml", { type: "application/yaml" });
      Object.defineProperty(file, "text", { value: async () => text });
      fireEvent.change(within(dialog).getByLabelText(/Spec/), { target: { files: [file] } });
      expect(
        await within(dialog).findByText(
          /Couldn't read the spec: a mapping value isn't allowed here/,
        ),
      ).toBeInTheDocument();
      expect(within(dialog).getByText("openapi.yaml · line 3")).toBeInTheDocument();
      expect(within(dialog).getByText("/a: b: c").closest("[data-line]")).toHaveAttribute(
        "data-line",
        "3",
      );
    },
  );

  acceptance(
    "web-ui",
    "re-importing a spec previews the operations it adds and removes",
    async () => {
      api.previewReimport.mockResolvedValue({
        title: "Billing API",
        version: "2.4.0",
        added: [
          {
            key: "GET /refunds",
            summary: null,
            source: { start_line: 10, end_line: 12, text: '"/refunds": {\n  "get": {}\n}' },
            tool: { name: "list_refunds", method: "GET", path: "/refunds" },
          },
          {
            key: "POST /refunds",
            summary: null,
            source: null,
            tool: { name: "create_refund", method: "POST", path: "/refunds" },
          },
        ],
        removed: ["create_invoice"],
        kept: ["get_invoice"],
        changed: [
          {
            name: "get_invoice",
            operation: "GET /invoices/{id}",
            method: "GET",
            path: "/invoices/{id}",
            new_required: ["currency"],
            request_changed: false,
            old_text: '"required": ["id"]',
            new_text: '"required": ["id", "currency"]',
            new_start_line: 412,
            new_end_line: 412,
          },
        ],
        warnings: [],
      });
      api.applyReimport.mockResolvedValue(billing);
      renderAt("/custom-tools/billing");
      fireEvent.click(await screen.findByRole("button", { name: "Re-import" }));
      const dialog = await screen.findByRole("dialog", { name: "Re-import billing" });
      const preview = await within(dialog).findByTestId("reimport-preview");
      expect(within(preview).getByText("4 changes in billing")).toBeInTheDocument();
      expect(within(dialog).getByText(/Billing API 2.3.0 → 2.4.0/)).toBeInTheDocument();

      // What will happen, in words.
      expect(within(preview).getByText(/becomes a tool, on\./)).toBeInTheDocument();
      expect(within(preview).getByText(/changes data, so it isn't added/)).toBeInTheDocument();
      expect(
        within(preview).getByText(/gets a new required argument, currency/),
      ).toBeInTheDocument();
      expect(
        within(preview).getByText(/is gone from the spec; agents lose it/),
      ).toBeInTheDocument();

      // A read starts ticked, a write does not; the first change's diff is on the right.
      expect(within(preview).getByRole("checkbox", { name: "Add list_refunds" })).toBeChecked();
      expect(
        within(preview).getByRole("checkbox", { name: "Add create_refund" }),
      ).not.toBeChecked();
      expect(within(dialog).getByText(/0 tools are unchanged/)).toBeInTheDocument();
      expect(api.applyReimport).not.toHaveBeenCalled();
      fireEvent.click(within(preview).getByRole("button", { name: /get_invoice/ }));
      expect(await within(dialog).findByText(/@@ -412,1 \+412,1 @@/)).toBeInTheDocument();
      expect(
        within(dialog).getByText(/After you apply, agents must pass currency/),
      ).toBeInTheDocument();

      // Ticking the write adds it to what Apply sends.
      fireEvent.click(within(preview).getByRole("checkbox", { name: "Add create_refund" }));
      expect(within(dialog).getByRole("button", { name: "Apply 4 changes" })).toBeInTheDocument();
      fireEvent.click(within(preview).getByRole("checkbox", { name: "Add create_refund" }));
      fireEvent.click(within(dialog).getByRole("button", { name: "Apply 3 changes" }));
      await waitFor(() =>
        expect(api.applyReimport).toHaveBeenCalledWith("billing", ["GET /refunds"], undefined),
      );
    },
  );
});
