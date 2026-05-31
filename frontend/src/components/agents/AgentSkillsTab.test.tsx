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

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(() => ({
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
            link_mode: null,
          },
        ],
      },
      // A skill not bound to this agent must NOT appear in the section.
      { name: "other", description: "", bindings: [] },
    ],
    isPending: false,
    error: null,
  })),
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

describe("AgentSkillsTab", () => {
  test("lists the skill bound to this agent with a toggle switch", () => {
    // AgentInstallSkillsDialog + AgentSkillsBulkActions now run via useBulkMutate,
    // which reads the QueryClient — provide one even though no bulk op fires here.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AgentSkillsTab agent={AGENT} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByText("other")).not.toBeInTheDocument();

    const sw = screen.getByRole("switch");
    expect(sw).toBeInTheDocument();
    expect(sw).toBeChecked();
  });
});
