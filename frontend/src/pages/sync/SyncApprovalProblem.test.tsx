// frontend/src/pages/sync/SyncApprovalProblem.test.tsx
//
// A round whose push token waits for approval in the desktop app is not a
// refused sign-in: the card says the token waits, and offers Secrets.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { SyncProblemBanner } from "./SyncProblemBanner";
import { primaryAction, syncState } from "./syncPageState";
import { makeRound, makeStatus } from "./syncTestKit";

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
  test("the card names the cause, offers Secrets and a retry", () => {
    const onRun = vi.fn();
    render(
      <MemoryRouter>
        <SyncProblemBanner status={STATUS} runs={[]} onRun={onRun} running={false} />
      </MemoryRouter>,
    );
    const card = within(screen.getByTestId("sync-problem"));
    expect(card.getByText("The push token is waiting for your approval")).toBeInTheDocument();
    expect(card.getByText("sync-token")).toBeInTheDocument();
    expect(card.getByRole("link", { name: "Open in Secrets" })).toHaveAttribute("href", "/secrets");
    fireEvent.click(card.getByRole("button", { name: /try again|retry/i }));
    expect(onRun).toHaveBeenCalled();
  });

  test("the page state is its own, not a sign-in failure", () => {
    const state = syncState(STATUS);
    expect(state.kind).toBe("waiting_approval");
    expect(state.tone).toBe("warn");
    expect(primaryAction(state.kind).label).toBe("tryAgain");
  });
});
