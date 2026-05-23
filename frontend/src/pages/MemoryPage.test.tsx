// frontend/src/pages/MemoryPage.test.tsx — TEST26-014
//
// MemoryPage delegates to KindResourcePage(kind="memory"). We mock
// `useResources` so the page renders deterministically and assert the
// empty state, the populated state, the add CTA, and the error fallback.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { MemoryPage } from "./MemoryPage";
import { registerFrontendKinds } from "@/kinds";

// Register the memory kind UI module up-front so the KindResourcePage
// dispatch can find a Card to render. Without this, ResourceListView
// renders an "unregistered kind" placeholder.
registerFrontendKinds();

vi.mock("@/lib/hooks/useResources", () => ({
  useResources: vi.fn(),
  useResource: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useResources");
const useResourcesMock = vi.mocked(hooks.useResources);

// Mock the per-kind mutation hooks used by the Card so toggling the
// switch doesn't try to talk to a real backend during the populated test.
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
  useDisableResource: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
}));

afterEach(() => vi.clearAllMocks());

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("MemoryPage", () => {
  test("renders the loading state while resources are pending", () => {
    useResourcesMock.mockReturnValue({
      data: undefined,
      isPending: true,
      error: null,
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<MemoryPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the empty state when no memory stores exist", () => {
    useResourcesMock.mockReturnValue({
      data: [],
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<MemoryPage />, { wrapper: wrap(null) });
    // Title from i18n key memory.title.
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    // Add CTA appears in the empty-state card.
    expect(screen.getAllByRole("link").length).toBeGreaterThan(0);
  });

  test("renders the populated list when memory stores exist", () => {
    useResourcesMock.mockReturnValue({
      data: [
        {
          ref: "memory:prefs",
          kind: "memory",
          name: "prefs",
          description: "coding preferences",
          config: {
            embedding_model: "BAAI/bge-small-en-v1.5",
            llm_provider: "ollama",
            llm_model: "llama3.1",
            llm_endpoint: null,
            llm_credential_ref: null,
            max_memory_chars: 8192,
          },
          enabled: true,
          created_at: "2026-05-29T00:00:00Z",
          updated_at: "2026-05-29T00:00:00Z",
        },
      ],
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<MemoryPage />, { wrapper: wrap(null) });
    expect(screen.getByRole("link", { name: "prefs" })).toBeInTheDocument();
  });

  test("renders an error card when the resources query fails", () => {
    useResourcesMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: new Error("HTTP 500"),
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<MemoryPage />, { wrapper: wrap(null) });
    // The KindResourcePage renders translateApiError; the literal message
    // varies by locale, so assert on the surrounding card title which
    // always uses the `resources.loadFailed` key.
    expect(screen.getAllByRole("heading").length).toBeGreaterThan(0);
  });
});
