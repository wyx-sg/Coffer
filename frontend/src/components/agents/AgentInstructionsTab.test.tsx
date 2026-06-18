// frontend/src/components/agents/AgentInstructionsTab.test.tsx
//
// The "Instructions" tab edits the master document and shows per-agent delivery
// status with deliver/remove/adopt actions. We mock the useAgents hooks so the
// component renders deterministically.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentInstructionsTab } from "./AgentInstructionsTab";

const setMasterMutate = vi.fn().mockResolvedValue({ content: "x", fingerprint: "fp2" });
const deliverMutate = vi.fn().mockResolvedValue({ delivered: true, in_sync: true });
const adoptMutate = vi.fn().mockResolvedValue({ content: "x", fingerprint: "fp3" });

let statusValue: { data?: { delivered: boolean; in_sync: boolean }; isError: boolean } = {
  data: { delivered: true, in_sync: false },
  isError: false,
};

vi.mock("@/lib/hooks/useAgentInstructions", () => ({
  useMasterInstructions: () => ({
    data: { content: "house rules", fingerprint: "fp1" },
    isLoading: false,
  }),
  useAgentInstructionsStatus: () => statusValue,
  useSetMasterInstructions: () => ({ mutateAsync: setMasterMutate, isPending: false }),
  useDeliverInstructions: () => ({ mutateAsync: deliverMutate, isPending: false }),
  useAdoptInstructions: () => ({ mutateAsync: adoptMutate, isPending: false }),
}));

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

afterEach(() => {
  vi.clearAllMocks();
  statusValue = { data: { delivered: true, in_sync: false }, isError: false };
});

describe("AgentInstructionsTab", () => {
  test("shows the master content, drift status, and delivers", async () => {
    render(<AgentInstructionsTab name="claude" />, { wrapper: wrap });

    // Master content is loaded into the editor.
    expect(screen.getByLabelText("Master instructions")).toHaveValue("house rules");
    // Delivered-but-drifted status is surfaced.
    expect(screen.getByTestId("instructions-status")).toHaveTextContent("master has changed");

    // Saving the master passes the fingerprint for stale-write protection.
    fireEvent.click(screen.getByRole("button", { name: "Save master" }));
    await waitFor(() =>
      expect(setMasterMutate).toHaveBeenCalledWith({
        content: "house rules",
        expected_fingerprint: "fp1",
      }),
    );

    // Deliver writes the block.
    fireEvent.click(screen.getByRole("button", { name: "Deliver" }));
    await waitFor(() => expect(deliverMutate).toHaveBeenCalledWith(true));

    // Remove strips the block (deliver hook called with `false`).
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(deliverMutate).toHaveBeenCalledWith(false));

    // Adopt pulls this agent's instructions into the master.
    fireEvent.click(screen.getByRole("button", { name: "Adopt into master" }));
    await waitFor(() => expect(adoptMutate).toHaveBeenCalled());
  });

  test("an agent without an instructions file shows the unsupported notice", () => {
    statusValue = { isError: true };
    render(<AgentInstructionsTab name="openclaw" />, { wrapper: wrap });
    expect(screen.getByText(/no instructions file to manage/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deliver" })).not.toBeInTheDocument();
  });
});
