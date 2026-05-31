// frontend/src/kinds/memory/MemoryStoreCard.test.tsx — TEST26-014
//
// Renders the MemoryStoreCard with sample data and asserts on the
// llm_provider badge, the optional description, the enable/disable
// switch wiring, and the resource detail link.

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { MemoryStoreCard } from "./MemoryStoreCard";
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

describe("MemoryStoreCard", () => {
  test("renders the store name as a link to its detail page", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<MemoryStoreCard resource={makeResource()} />);
    render(<Wrapper />);

    const link = screen.getByRole("link", { name: "prefs" });
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toBe("/memory/prefs");
  });

  test("shows the LLM provider badge", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<MemoryStoreCard resource={makeResource()} />);
    render(<Wrapper />);
    expect(screen.getByText(/LLM: ollama/i)).toBeInTheDocument();
  });

  test("falls back to 'none' when llm_provider is missing from config", () => {
    _stubMutationHooks();
    const r = makeResource({
      config: {
        embedding_model: "m",
        max_memory_chars: 8192,
      } as ResourceOut["config"],
    });
    const Wrapper = wrap(<MemoryStoreCard resource={r} />);
    render(<Wrapper />);
    expect(screen.getByText(/LLM: none/i)).toBeInTheDocument();
  });

  test("renders the description when provided", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<MemoryStoreCard resource={makeResource()} />);
    render(<Wrapper />);
    expect(screen.getByText("coding preferences")).toBeInTheDocument();
  });

  test("does not render a description block when empty", () => {
    _stubMutationHooks();
    const r = makeResource({ description: null });
    const Wrapper = wrap(<MemoryStoreCard resource={r} />);
    render(<Wrapper />);
    expect(screen.queryByText("coding preferences")).not.toBeInTheDocument();
  });

  test("toggle: disable -> calls disable.mutate when an enabled card is switched off", () => {
    const { disableMutate } = _stubMutationHooks();
    const Wrapper = wrap(<MemoryStoreCard resource={makeResource({ enabled: true })} />);
    render(<Wrapper />);
    const sw = screen.getByRole("switch", { name: "disable" });
    fireEvent.click(sw);
    expect(disableMutate).toHaveBeenCalledWith({
      kind: "memory",
      name: "prefs",
    });
  });

  test("toggle: enable -> calls enable.mutate when a disabled card is switched on", () => {
    const { enableMutate } = _stubMutationHooks();
    const Wrapper = wrap(<MemoryStoreCard resource={makeResource({ enabled: false })} />);
    render(<Wrapper />);
    const sw = screen.getByRole("switch", { name: "enable" });
    fireEvent.click(sw);
    expect(enableMutate).toHaveBeenCalledWith({
      kind: "memory",
      name: "prefs",
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
    const Wrapper = wrap(<MemoryStoreCard resource={makeResource({ enabled: false })} />);
    render(<Wrapper />);
    expect(screen.getByRole("switch", { name: "enable" })).toBeDisabled();
  });
});
