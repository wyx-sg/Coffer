// frontend/src/components/mcp/invocationsTabs.test.tsx
// A server's Invocations tab and Activity's MCP calls tab are one table, not
// two kept in step: both surfaces mount InvocationsTable, the server's scoped
// to its uid and Activity's unscoped. (What the table then does in each scope
// is pinned in InvocationsTable.test.tsx.)
import { expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { McpServerDetailTabs } from "./McpServerDetailTabs";
import { ActivityPage } from "@/pages/activity/ActivityPage";

const mounted = vi.fn();
vi.mock("./InvocationsTable", () => ({
  InvocationsTable: (props: { serverUid?: string; enabled?: boolean }) => {
    mounted(props);
    return <div>invocation table</div>;
  },
}));
vi.mock("./CapabilityList", () => ({ CapabilityList: () => null }));
vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn(() => ({ GET: vi.fn() })) }));

function renderAt(path: string, ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

acceptance("web-ui", "a server's invocations tab is the Activity calls table scoped to it", () => {
  const detail = renderAt(
    "/mcp-servers/u-1?tab=invocations",
    <McpServerDetailTabs
      serverUid="u-1"
      capabilities={undefined}
      config={{}}
      isCapsPending={false}
      onRefresh={vi.fn()}
    />,
  );
  expect(mounted).toHaveBeenCalled();
  expect(mounted.mock.lastCall![0]).toEqual({ serverUid: "u-1" });
  detail.unmount();

  mounted.mockClear();
  renderAt("/activity?tab=mcp", <ActivityPage />);
  expect(mounted).toHaveBeenCalled();
  const activityProps = mounted.mock.lastCall![0];
  expect(activityProps.serverUid).toBeUndefined();
  expect(activityProps.enabled).toBe(true);
});
