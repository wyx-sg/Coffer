// frontend/src/kinds/knowledge/KnowledgeScopeCard.test.tsx
//
// Renders the KnowledgeScopeCard with sample data and asserts on the scope badge
// (no llm_provider anymore), the optional description, the enable/disable
// switch wiring, and the resource detail link.

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { KnowledgeScopeCard } from "./KnowledgeScopeCard";
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
    ref: "memory:project-x",
    kind: "knowledge",
    name: "project-x",
    description: "project facts",
    config: { scope: "project", retrieval_modes: ["grep", "keyword"], default_mode: "keyword" },
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

describe("KnowledgeScopeCard", () => {
  test("renders the scope name as a link to its detail page", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeScopeCard resource={makeResource()} />);
    render(<Wrapper />);

    const link = screen.getByRole("link", { name: "project-x" });
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toBe("/knowledge/project-x");
  });

  test("shows the scope badge from an explicit config.scope", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeScopeCard resource={makeResource()} />);
    render(<Wrapper />);
    expect(screen.getByText("Project")).toBeInTheDocument();
  });

  test("derives 'global' from the reserved `global` resource name", () => {
    _stubMutationHooks();
    const r = makeResource({ name: "global", config: {} as ResourceOut["config"] });
    const Wrapper = wrap(<KnowledgeScopeCard resource={r} />);
    render(<Wrapper />);
    expect(screen.getByText("Global")).toBeInTheDocument();
  });

  test("derives 'named' for a collection the user created", () => {
    _stubMutationHooks();
    const r = makeResource({ name: "design-notes", config: {} as ResourceOut["config"] });
    const Wrapper = wrap(<KnowledgeScopeCard resource={r} />);
    render(<Wrapper />);
    expect(screen.getByText("Collection")).toBeInTheDocument();
  });

  test("derives 'project' from a project-<ULID> resource name", () => {
    _stubMutationHooks();
    const r = makeResource({
      name: "project-01HXYZPROJECTULID000000000",
      config: {} as ResourceOut["config"],
    });
    const Wrapper = wrap(<KnowledgeScopeCard resource={r} />);
    render(<Wrapper />);
    expect(screen.getByText("Project")).toBeInTheDocument();
  });

  test("never silently labels a non-global scope 'Global'", () => {
    _stubMutationHooks();
    // A generic resource row carries no typed `scope` and no project_id; the
    // name still decides, so this must not fall through to "Global".
    const r = makeResource({ config: {} as ResourceOut["config"] });
    const Wrapper = wrap(<KnowledgeScopeCard resource={r} />);
    render(<Wrapper />);
    expect(screen.getByText("Project")).toBeInTheDocument();
    expect(screen.queryByText("Global")).not.toBeInTheDocument();
  });

  test("renders the description when provided", () => {
    _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeScopeCard resource={makeResource()} />);
    render(<Wrapper />);
    expect(screen.getByText("project facts")).toBeInTheDocument();
  });

  test("does not render a description block when empty", () => {
    _stubMutationHooks();
    const r = makeResource({ description: null });
    const Wrapper = wrap(<KnowledgeScopeCard resource={r} />);
    render(<Wrapper />);
    expect(screen.queryByText("project facts")).not.toBeInTheDocument();
  });

  test("toggle: disable -> calls disable.mutate when an enabled card is switched off", () => {
    const { disableMutate } = _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeScopeCard resource={makeResource({ enabled: true })} />);
    render(<Wrapper />);
    fireEvent.click(screen.getByRole("switch", { name: "disable" }));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "knowledge", name: "project-x" });
  });

  test("toggle: enable -> calls enable.mutate when a disabled card is switched on", () => {
    const { enableMutate } = _stubMutationHooks();
    const Wrapper = wrap(<KnowledgeScopeCard resource={makeResource({ enabled: false })} />);
    render(<Wrapper />);
    fireEvent.click(screen.getByRole("switch", { name: "enable" }));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "knowledge", name: "project-x" });
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
    const Wrapper = wrap(<KnowledgeScopeCard resource={makeResource({ enabled: false })} />);
    render(<Wrapper />);
    expect(screen.getByRole("switch", { name: "enable" })).toBeDisabled();
  });
});
