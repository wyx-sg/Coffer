// frontend/src/pages/KindResourcePage.test.tsx
//
// Kind-scoped resource landing page: header (+ optional add CTA from the
// kind registry), loading / error / populated / empty states. `useResources`
// is mocked; a synthetic kind with an addPath is registered so both CTA
// branches are exercised without depending on real kind modules.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { Library } from "lucide-react";

import { KindResourcePage } from "./KindResourcePage";
import { registerKindUI, type ResourceOut } from "@/lib/components/kindRegistry";

vi.mock("@/lib/hooks/useResources", () => ({
  useResources: vi.fn(),
  useResource: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useResources");
const useResourcesMock = vi.mocked(hooks.useResources);

// A self-contained kind so ResourceListView has a Card and the page has an
// addPath (knowledge_base/memory register no addPath).
registerKindUI({
  name: "test_kind",
  displayName: "Test Kind",
  Card: ({ resource }: { resource: ResourceOut }) => <div>card:{resource.name}</div>,
  addPath: "/test-kind/new",
});

afterEach(() => vi.clearAllMocks());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderPage() {
  // The i18n namespace is irrelevant to the states under test; reuse the
  // knowledgeBases keys so title/subtitle/add/empty all resolve.
  return render(<KindResourcePage kind="test_kind" icon={Library} i18nKey="knowledgeBases" />, {
    wrapper: wrap(),
  });
}

const RESOURCE = {
  ref: "test_kind:alpha",
  kind: "test_kind",
  name: "alpha",
  description: null,
  config: {},
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

describe("KindResourcePage", () => {
  test("renders the loading state while resources are pending", () => {
    useResourcesMock.mockReturnValue({
      data: undefined,
      isPending: true,
      error: null,
    } as unknown as ReturnType<typeof hooks.useResources>);

    renderPage();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders an error card when the resources query fails", () => {
    useResourcesMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: new Error("HTTP 500"),
    } as unknown as ReturnType<typeof hooks.useResources>);

    renderPage();
    expect(screen.getByText("Failed to load resources")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
  });

  test("renders the kind's cards and the header add CTA when populated", () => {
    useResourcesMock.mockReturnValue({
      data: [RESOURCE],
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof hooks.useResources>);

    renderPage();
    expect(screen.getByText("card:alpha")).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: /new knowledge base/i });
    expect(cta).toHaveAttribute("href", "/test-kind/new");
  });

  test("renders the empty state with the add CTA when no resources exist", () => {
    useResourcesMock.mockReturnValue({
      data: [],
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof hooks.useResources>);

    renderPage();
    expect(screen.getByText(/no knowledge bases yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /new knowledge base/i })).toBeInTheDocument();
  });
});
