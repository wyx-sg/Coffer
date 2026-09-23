// frontend/src/pages/listStates.test.tsx
// Empty, loading and error are first-class on a list surface: the page header
// stays up over skeleton rows while the query is pending, and a failed query is
// an error card with a readable message — never a blank page. Driven through
// the real MCP servers page and its real table; only the data hook is stubbed.
import { afterEach, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { ResourcesPage } from "./ResourcesPage";
import { SkillsPage } from "./SkillsPage";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useResources", () => ({ useResources: vi.fn() }));
vi.mock("@/components/mcp/AddMcpServerDialog", () => ({
  AddMcpServerDialog: () => <button>add mcp server</button>,
}));

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(() => ({ data: [], isPending: false, error: null, refetch: vi.fn() })),
  useImportSkill: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, error: null })),
  useRemoveSkill: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const { useResources } = await import("@/lib/hooks/useResources");

function stub(state: { isPending?: boolean; error?: unknown }) {
  vi.mocked(useResources).mockReturnValue({
    data: undefined,
    isPending: state.isPending ?? false,
    error: state.error ?? null,
  } as unknown as ReturnType<typeof useResources>);
}

function renderPage(page: React.ReactNode = <ResourcesPage />) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

acceptance("web-ui", "a list surface shows first-class loading and error states", () => {
  stub({ isPending: true });
  const pending = renderPage();
  expect(screen.getByRole("heading", { level: 1, name: "MCP servers" })).toBeInTheDocument();
  // Skeleton rows in the real table, not a blank page or a bare "Loading…".
  expect(
    document.querySelectorAll('[data-slot="skeleton"], .animate-pulse').length,
  ).toBeGreaterThan(0);
  expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  pending.unmount();

  stub({ error: new ApiError("RESOURCE_NOT_FOUND", "no such thing") });
  renderPage();
  expect(screen.getByRole("heading", { level: 1, name: "MCP servers" })).toBeInTheDocument();
  expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  expect(screen.getByText("Resource not found")).toBeInTheDocument();
});

acceptance("web-ui", "page headers share one typographic scale", () => {
  /** The page's one h1 and its subtitle, read off a rendered page. */
  const header = (page: React.ReactNode) => {
    const view = renderPage(page);
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    const subtitle = h1s[0].closest("header")!.querySelector("p")!;
    const out = {
      title: h1s[0].textContent,
      titleClass: h1s[0].className,
      subtitleClass: subtitle.className,
    };
    view.unmount();
    return out;
  };

  vi.mocked(useResources).mockReturnValue({
    data: [],
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useResources>);
  const mcp = header(<ResourcesPage />);
  const skills = header(<SkillsPage />);

  expect([mcp.title, skills.title]).toEqual(["MCP servers", "Skills"]);
  expect(skills.titleClass).toBe(mcp.titleClass);
  expect(skills.subtitleClass).toBe(mcp.subtitleClass);
  expect(mcp.subtitleClass).not.toBe(mcp.titleClass);
});
