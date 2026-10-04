// frontend/src/pages/sync/SyncApprovalProblem.test.tsx
//
// A round whose push token waits for approval in the desktop app is not a
// refused sign-in: the card says the token waits, and Review opens the global
// approvals dialog.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { SyncProblemBanner } from "./SyncProblemBanner";
import { primaryAction, syncState } from "./syncPageState";
import { makeRound, makeStatus } from "./syncTestKit";

vi.mock("./useSyncIgnore", async (orig) => ({
  ...(await orig<typeof import("./useSyncIgnore")>()),
  useSyncIgnore: () => ({ isIgnored: () => false, ignorer: () => undefined }),
}));
vi.mock("@/lib/hooks/useApprovals", () => ({ openApprovalsSheet: vi.fn() }));

const { openApprovalsSheet } = await import("@/lib/hooks/useApprovals");
afterEach(() => vi.clearAllMocks());

const STATUS = makeStatus({
  last_round: makeRound({ status: "auth_failed" }),
  problem: {
    kind: "waiting_approval",
    message: "the push token sync-token is waiting for approval in the Coffer desktop app",
    secret_ref: "sync-token",
    since: null,
    handoff: null,
    plaintext: [],
  },
});

describe("waiting for approval", () => {
  test("the card names the cause and Review opens the approvals dialog", () => {
    render(
      <MemoryRouter>
        <SyncProblemBanner status={STATUS} runs={[]} onRecheck={vi.fn()} rechecking={false} />
      </MemoryRouter>,
    );
    const card = within(screen.getByTestId("sync-problem"));
    expect(card.getByText("The push token is waiting for your approval")).toBeInTheDocument();
    expect(card.getByText("sync-token")).toBeInTheDocument();
    // No Retry in a card: the header's Sync now is the one way to run a round.
    expect(card.queryByRole("button", { name: /retry|try again/i })).toBeNull();
    fireEvent.click(card.getByRole("button", { name: "Review" }));
    expect(openApprovalsSheet).toHaveBeenCalled();
  });

  test("the page state is its own, not a sign-in failure", () => {
    const state = syncState(STATUS);
    expect(state.kind).toBe("waiting_approval");
    expect(state.tone).toBe("warn");
    expect(primaryAction(state.kind)).toEqual({ syncing: false, disabled: false });
  });
});
