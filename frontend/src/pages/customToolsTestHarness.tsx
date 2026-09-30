// src/pages/customToolsTestHarness.tsx — what the Custom tools page tests share: the groups they render,
// the router they render in, and the mocked API. Each test file declares the vi.mock calls (they are
// hoisted per file); this module reads the mocked functions back.
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

import { makeGroup, makeTool } from "@/components/custom-tools/testFixtures";
import { customToolsApi } from "@/lib/api/customTools";
import { CustomToolsPage } from "./CustomToolsPage";

export const api = customToolsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

export const grafana = makeGroup({
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
export const deploy = makeGroup({ name: "deploy-api", health: "failing" });
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
      reach_override: ["ag-cc"],
    }),
  ],
});
export const status = makeGroup({ name: "status-page", enabled: false, health: "off" });
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
}
