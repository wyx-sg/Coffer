// frontend/src/components/agents/AgentSkillsTab.test.tsx
//
// The Skills tab's "Managed by Coffer" section lists every skill that has a
// binding for THIS agent, each with an enable/disable Switch reflecting the
// binding's enabled state. (AgentInstallSkillsDialog also reads useSkills, so
// the single mock below covers both.)
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentSkillsTab } from "./AgentSkillsTab";
import type { AgentOut } from "@/lib/api/agents";
import type { LinkMode } from "@/lib/api/skills";

const useSkillsMock = vi.fn();

function mockBinding(linkMode: LinkMode | null) {
  return {
    data: [
      {
        name: "hello",
        description: "hi",
        bindings: [
          {
            agent_name: "cc",
            enabled: true,
            last_linked_at: null,
            last_link_path: null,
            link_mode: linkMode,
          },
        ],
      },
      // A skill not bound to this agent must NOT appear in the section.
      { name: "other", description: "", bindings: [] },
    ],
    isPending: false,
    error: null,
  };
}

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: () => useSkillsMock(),
  useEnableSkill: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableSkill: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const AGENT: AgentOut = {
  name: "cc",
  type: "claude_code",
  config_dir: "/x",
  description: null,
  created_at: "",
  updated_at: "",
};

afterEach(() => vi.clearAllMocks());

function renderTab() {
  // AgentInstallSkillsDialog + AgentSkillsBulkActions now run via useBulkMutate,
  // which reads the QueryClient — provide one even though no bulk op fires here.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AgentSkillsTab agent={AGENT} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgentSkillsTab", () => {
  test("lists the skill bound to this agent with a toggle switch", () => {
    useSkillsMock.mockReturnValue(mockBinding(null));
    renderTab();

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByText("other")).not.toBeInTheDocument();

    const sw = screen.getByRole("switch");
    expect(sw).toBeInTheDocument();
    expect(sw).toBeChecked();
  });

  test("shows a degraded warning chip when the binding fell back to a copy", () => {
    // FR-012: when symlink/junction delivery isn't available Coffer copies the
    // skill instead; the UI MUST surface that the binding is degraded.
    useSkillsMock.mockReturnValue(mockBinding("copy_fallback"));
    renderTab();

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByTestId("skill-degraded-badge")).toBeInTheDocument();
  });

  test("does NOT show the degraded chip for a normal symlink binding", () => {
    useSkillsMock.mockReturnValue(mockBinding("symlink"));
    renderTab();

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByTestId("skill-degraded-badge")).not.toBeInTheDocument();
  });
});
