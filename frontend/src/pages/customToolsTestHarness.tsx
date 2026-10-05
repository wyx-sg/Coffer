// src/pages/customToolsTestHarness.tsx — what the Custom tools page tests share: the groups they render,
// the router they render in, and the mocked API (the group routes, and the MCP server reads a group's Overview
// and Tools tab make by its uid). Each test file declares the vi.mock calls (they are hoisted per file); this
// module reads the mocked functions back.
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

import { makeGroup, makeTool } from "@/components/custom-tools/testFixtures";
import { customToolsApi } from "@/lib/api/customTools";
import { mcpServersApi } from "@/lib/api/mcpServers";
import { CustomToolsPage } from "./CustomToolsPage";

export const api = customToolsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
export const mcp = mcpServersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

/** billing's last 24 hours: Claude Code's calls, one failed. */
const billingSummary = {
  since: "2026-10-04T10:00:00Z",
  calls: 31,
  errors: 1,
  last_call_at: "2026-10-05T09:58:00Z",
  by_agent: [{ agent_uid: "ag-cc", calls: 31, errors: 1, last_call_at: "2026-10-05T09:58:00Z" }],
  by_tool: [{ tool: "get_invoice", calls: 31, errors: 1, last_call_at: "2026-10-05T09:58:00Z" }],
};

/** billing's tiering: both tools listed, create_invoice pinned. */
const billingTiering = {
  enabled: true,
  budget: 50,
  catalogue_size: 2,
  listed_count: 2,
  tool_count: 2,
  listed: ["get_invoice", "create_invoice"],
  behind_search: [],
  tools: [
    { tool: "get_invoice", mode: "auto", effective: "listed", reason: "within_budget" },
    { tool: "create_invoice", mode: "listed", effective: "listed", reason: "pinned" },
  ],
};

const grafana = makeGroup({
  name: "grafana",
  health: "attention",
  health_reason: "secret_missing",
  secret_state: "missing",
  headers: [
    {
      name: "Authorization",
      value: null,
      secret: "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
      secret_state: "missing",
    },
  ],
  tools: [makeTool({ name: "search_dashboards", path: "/search" })],
});
const deploy = makeGroup({ name: "deploy-api", health: "failing" });
export const billing = makeGroup({
  name: "billing",
  source: {
    kind: "url",
    location: "https://billing.internal.example/openapi.json",
    title: "Billing API",
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
    }),
  ],
});
const status = makeGroup({ name: "status-page", enabled: false, health: "off" });
const ALL = [billing, status, grafana, deploy];

let current = "";
// A test-only module: fast refresh never loads it.
// eslint-disable-next-line react-refresh/only-export-components
function LocationProbe() {
  current = useLocation().pathname;
  return null;
}
export const location = () => current;

export function renderAt(path: string) {
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

export function resetCustomToolMocks() {
  vi.clearAllMocks();
  api.list.mockResolvedValue(ALL);
  api.get.mockImplementation(async (name: string) => ALL.find((g) => g.name === name));
  mcp.summary.mockResolvedValue(billingSummary);
  mcp.tiering.mockResolvedValue(billingTiering);
  mcp.setToolExposure.mockResolvedValue(undefined);
}
