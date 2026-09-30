// src/lib/hooks/useClis.test.tsx — the CLIs entry's attention dot in the sidebar.
//
// Real QueryClientProvider and the real SidebarNav; only the api modules are mocked.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { SidebarNav } from "@/components/SidebarNav";
import { TooltipProvider } from "@/components/ui/tooltip";
import { GH_OUTDATED, UV_READY } from "@/test/cliFixtures";

vi.mock("@/lib/api/clis", () => ({
  clisApi: { list: vi.fn() },
}));
// The Sync dot's own read; kept quiet so only the CLIs signal is under test.
vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: () => ({ data: undefined, isError: false }),
}));
vi.mock("@/lib/hooks/useFeatures", () => ({
  useFeatureEnabled: () => true,
}));
const { clisApi } = await import("@/lib/api/clis");
const api = vi.mocked(clisApi);

function renderNav() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <TooltipProvider>
          <SidebarNav collapsed={false} pathname="/" />
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("the CLIs attention dot", () => {
  // scenario (web-ui, revise-web-ui-ia 7.14d): "overview flags a required CLI that needs attention" (the sidebar half)
  test("a required CLI that needs attention puts a dot on the CLIs entry", async () => {
    api.list.mockResolvedValue({ items: [GH_OUTDATED, UV_READY], warnings: [] });
    renderNav();
    expect(await screen.findByTestId("nav-dot-clis")).toHaveAccessibleName("Needs your attention");
  });

  test("no dot once every required CLI is ready", async () => {
    api.list.mockResolvedValue({ items: [UV_READY], warnings: [] });
    renderNav();
    await vi.waitFor(() => expect(api.list).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("nav-dot-clis")).toBeNull();
  });

  test("no dot when the list cannot be read", async () => {
    api.list.mockRejectedValue(new Error("offline"));
    renderNav();
    await vi.waitFor(() => expect(api.list).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("nav-dot-clis")).toBeNull();
  });
});
