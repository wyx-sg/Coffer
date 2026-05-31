// frontend/src/components/agents/AgentInstallSkillsDialog.test.tsx
//
// The bulk skill-picker dialog lists every Coffer-managed skill in a DataTable
// (search / filter / pagination / select-all). The "Install (N)" action lives
// in the selection bar — it only appears once ≥1 skill is checked, then binds
// each checked skill to every selected agent.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentInstallSkillsDialog } from "./AgentInstallSkillsDialog";
import type { AgentOut } from "@/lib/api/agents";

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(() => ({
    data: [
      {
        name: "hello",
        description: "hi",
        source: { type: "local_import", original_path: "/x" },
        bindings: [],
      },
    ],
    isPending: false,
  })),
}));

// AgentInstallSkillsDialog now installs via useBulkMutate (Promise.allSettled +
// summary toast), which reads the QueryClient for its single invalidation burst.
function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const AGENT: AgentOut = {
  name: "cur",
  type: "codex",
  config_dir: "/home/u/.codex",
  description: null,
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

afterEach(() => vi.clearAllMocks());

describe("AgentInstallSkillsDialog", () => {
  test("lists skills and reveals Install in the selection bar once a skill is checked", () => {
    render(<AgentInstallSkillsDialog agents={[AGENT]} open onOpenChange={() => {}} />, {
      wrapper: wrap(),
    });

    expect(screen.getByText("hello")).toBeInTheDocument();
    // No Install action until a skill is selected (the bar is hidden).
    expect(screen.queryByRole("button", { name: /^install \(/i })).not.toBeInTheDocument();

    // Checkboxes: [select-all, row]. Selecting the row reveals the bar + action.
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[checkboxes.length - 1]);
    expect(screen.getByRole("button", { name: /^install \(1\)/i })).toBeInTheDocument();
  });
});
