// frontend/src/components/reach/ReachControl.machineLocal.test.tsx
//
// The vault-sync half of the shared reach control: reach does not travel
// between machines, so the panel where it is set has to say so, and has to
// name a resource that is dormant here. The rest of the control's contract is
// resource-framework's and lives in ReachControl.test.tsx.
import { afterEach, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { ReachControl } from "./ReachControl";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const agentHooks = await import("@/lib/hooks/useAgents");

function seed() {
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: [
      { uid: "u-agent-7f21", name: "claude" },
      { uid: "u-agent-be04", name: "codex" },
    ],
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
}

function openOn(scope: string[] | null) {
  render(
    <ReachControl
      mode={scope === null ? "everywhere" : "restricted"}
      initialScope={{ agents: scope }}
      onDisabled={vi.fn()}
      onEverywhere={vi.fn()}
      onRestricted={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByTestId("scope-control").querySelector("button")!);
}

afterEach(() => vi.clearAllMocks());

acceptance("vault-sync", "the reach control says reach is machine-local", () => {
  seed();
  openOn([]);

  const line = screen.getByTestId("reach-machine-local");
  expect(line).toHaveTextContent(/this machine only/i);
  expect(line).toHaveTextContent(/not synced/i);
  // An empty agent list is named as dormant.
  expect(screen.getByText(/dormant/i)).toBeInTheDocument();
});
