// frontend/src/pages/settings/SecretBoundaryCard.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { OPEN_APPROVALS_EVENT } from "@/lib/hooks/useApprovals";
import { SecretBoundaryCard } from "./SecretBoundaryCard";

vi.mock("@/lib/api/credentials", () => ({
  credentialsApi: { pendingApprovals: vi.fn(), secretBoundary: vi.fn(), rejectApproval: vi.fn() },
}));
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => false,
  approvePending: vi.fn(),
  onApprovalsEvent: () => () => {},
}));
const { credentialsApi } = await import("@/lib/api/credentials");

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SecretBoundaryCard />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("SecretBoundaryCard", () => {
  test("says the protection is on and offers a way back to what waits", async () => {
    vi.mocked(credentialsApi.secretBoundary).mockResolvedValue({
      require_approval: true,
      pending_approval_id: null,
    });
    vi.mocked(credentialsApi.pendingApprovals).mockResolvedValue({
      approvals: [
        {
          id: "a1",
          op: "bind",
          status: "pending",
          description: "send secret",
          created_at: "2026-09-30T08:00:00Z",
          requested_by: "cli",
        },
      ],
    } as never);
    const opened = vi.fn();
    window.addEventListener(OPEN_APPROVALS_EVENT, opened);
    renderCard();

    expect(await screen.findByText(/new destinations wait for your approval/i)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /review/i }));
    expect(opened).toHaveBeenCalledTimes(1);
    window.removeEventListener(OPEN_APPROVALS_EVENT, opened);
  });

  test("shows nothing to review while nothing waits", async () => {
    vi.mocked(credentialsApi.secretBoundary).mockResolvedValue({
      require_approval: false,
      pending_approval_id: null,
    });
    vi.mocked(credentialsApi.pendingApprovals).mockResolvedValue({ approvals: [] });
    renderCard();
    expect(await screen.findByText(/without asking/i)).toBeInTheDocument();
    expect(screen.queryByTestId("pending-approvals-entry")).not.toBeInTheDocument();
  });
});
