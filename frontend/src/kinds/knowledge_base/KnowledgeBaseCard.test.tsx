// frontend/src/kinds/knowledge_base/KnowledgeBaseCard.test.tsx — TEST22-019
//
// Renders the KnowledgeBaseCard with sample data and asserts on the
// embedding-model badge, the optional description, the enable/disable
// switch wiring, and the resource detail link.

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { KnowledgeBaseCard } from "./KnowledgeBaseCard";
import type { components } from "@/lib/api/types";

vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(),
  useDisableResource: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useResourceMutations");
const useEnableResourceMock = vi.mocked(hooks.useEnableResource);
const useDisableResourceMock = vi.mocked(hooks.useDisableResource);

type ResourceOut = components["schemas"]["ResourceOut"];

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function makeResource(overrides: Partial<ResourceOut> = {}): ResourceOut {
  return {
    ref: "knowledge_base:designs",
    kind: "knowledge_base",
    name: "designs",
    description: "team design notes",
    config: {
      embedding_model: "BAAI/bge-small-en-v1.5",
      chunk_size: 512,
      chunk_overlap: 64,
      max_document_bytes: 1024 * 1024,
    },
    enabled: true,
    created_at: "2026-05-29T00:00:00Z",
    updated_at: "2026-05-29T00:00:00Z",
    ...overrides,
  } as ResourceOut;
}

function _stubMutationHooks() {
  const enableMutate = vi.fn();
  const disableMutate = vi.fn();
  useEnableResourceMock.mockReturnValue({
    mutate: enableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useEnableResource>);
  useDisableResourceMock.mockReturnValue({
    mutate: disableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useDisableResource>);
  return { enableMutate, disableMutate };
}

describe("KnowledgeBaseCard", () => {
  test("renders the KB name as a link to its detail page", () => {
    _stubMutationHooks();
    const r = makeResource();
    const Wrapper = wrap(<KnowledgeBaseCard resource={r} />);
    render(<Wrapper />);

    const link = screen.getByRole("link", { name: "designs" });
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toBe("/knowledge-bases/designs");
  });

  test("shows the embedding model badge", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeBaseCard resource={makeResource()} />);
    render(<Wrapper />);
    expect(screen.getByText("BAAI/bge-small-en-v1.5")).toBeInTheDocument();
  });

  test("falls back to '?' when embedding_model is missing", () => {
    _stubMutationHooks();
    const r = makeResource({
      config: {
        chunk_size: 512,
        chunk_overlap: 64,
        max_document_bytes: 1024,
      } as ResourceOut["config"],
    });
    const Wrapper = wrap(<KnowledgeBaseCard resource={r} />);
    render(<Wrapper />);
    expect(screen.getByText("?")).toBeInTheDocument();
  });

  test("renders the description when provided", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeBaseCard resource={makeResource()} />);
    render(<Wrapper />);
    expect(screen.getByText("team design notes")).toBeInTheDocument();
  });

  test("does not render a description block when empty", () => {
    _stubMutationHooks();
    const r = makeResource({ description: null });
    const Wrapper = wrap(<KnowledgeBaseCard resource={r} />);
    render(<Wrapper />);
    expect(screen.queryByText("team design notes")).not.toBeInTheDocument();
  });

  test("toggle: disable -> calls disable.mutate when enabled card is switched off", () => {
    const { disableMutate } = _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeBaseCard resource={makeResource({ enabled: true })} />);
    render(<Wrapper />);
    const sw = screen.getByRole("switch", { name: "disable" });
    fireEvent.click(sw);
    expect(disableMutate).toHaveBeenCalledWith({
      kind: "knowledge_base",
      name: "designs",
    });
  });

  test("toggle: enable -> calls enable.mutate when a disabled card is switched on", () => {
    const { enableMutate } = _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeBaseCard resource={makeResource({ enabled: false })} />);
    render(<Wrapper />);
    const sw = screen.getByRole("switch", { name: "enable" });
    fireEvent.click(sw);
    expect(enableMutate).toHaveBeenCalledWith({
      kind: "knowledge_base",
      name: "designs",
    });
  });

  test("switch is disabled while a mutation is pending", () => {
    useEnableResourceMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
    } as unknown as ReturnType<typeof hooks.useEnableResource>);
    useDisableResourceMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useDisableResource>);
    const Wrapper = wrap(<KnowledgeBaseCard resource={makeResource({ enabled: false })} />);
    render(<Wrapper />);
    expect(screen.getByRole("switch", { name: "enable" })).toBeDisabled();
  });
});
