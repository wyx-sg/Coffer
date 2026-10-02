// frontend/src/pages/settings/SecretBoundaryCard.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { OPEN_APPROVALS_EVENT } from "@/lib/hooks/useApprovals";
import { ToastProvider } from "@/components/ui/toast";
import { SecretBoundaryCard } from "./SecretBoundaryCard";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    pendingApprovals: vi.fn(),
    secretBoundary: vi.fn(),
    setSecretBoundary: vi.fn(),
    rejectApproval: vi.fn(),
  },
}));
const presence = vi.hoisted(() => ({ available: false, approvePending: vi.fn() }));
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => presence.available,
  approvePending: presence.approvePending,
  onApprovalsEvent: () => () => {},
}));
const { secretsApi } = await import("@/lib/api/secret");

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <SecretBoundaryCard />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function state(requireApproval: boolean) {
  vi.mocked(secretsApi.secretBoundary).mockResolvedValue({
    require_approval: requireApproval,
    pending_approval_id: null,
  });
  vi.mocked(secretsApi.pendingApprovals).mockResolvedValue({ approvals: [] });
}

afterEach(() => {
  vi.clearAllMocks();
  presence.available = false;
});

describe("SecretBoundaryCard", () => {
  test("says the protection is on and offers a way back to what waits", async () => {
    state(true);
    vi.mocked(secretsApi.pendingApprovals).mockResolvedValue({
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

  test("shows the off state with nothing to review while nothing waits", async () => {
    state(false);
    renderCard();
    expect(await screen.findByText(/without asking/i)).toBeInTheDocument();
    expect(screen.getByRole("switch")).not.toBeChecked();
    expect(screen.queryByTestId("pending-approvals-entry")).not.toBeInTheDocument();
  });

  test("in a browser the switch is disabled and says to turn it off in the app", async () => {
    state(true);
    renderCard();
    expect(await screen.findByText(/turn off in the coffer desktop app/i)).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeDisabled();
  });

  test("turning it back on needs no presence, even in a browser", async () => {
    state(false);
    vi.mocked(secretsApi.setSecretBoundary).mockResolvedValue({
      require_approval: true,
      pending_approval_id: null,
    });
    renderCard();
    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    await waitFor(() => expect(secretsApi.setSecretBoundary).toHaveBeenCalledWith(true));
    expect(presence.approvePending).not.toHaveBeenCalled();
  });

  test("in the app, turning it off asks first, then applies it with the presence check", async () => {
    presence.available = true;
    state(true);
    vi.mocked(secretsApi.setSecretBoundary).mockResolvedValue({
      require_approval: true,
      pending_approval_id: "d1",
    });
    presence.approvePending.mockResolvedValue({});
    renderCard();
    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);

    expect(await screen.findByText(/without your approval/i)).toBeInTheDocument();
    expect(secretsApi.setSecretBoundary).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));

    await waitFor(() => expect(presence.approvePending).toHaveBeenCalledWith("d1"));
    expect(secretsApi.setSecretBoundary).toHaveBeenCalledWith(false);
    expect(secretsApi.rejectApproval).not.toHaveBeenCalled();
  });

  test("a cancelled presence check keeps it on, refuses what it asked, and shows why", async () => {
    presence.available = true;
    state(true);
    vi.mocked(secretsApi.setSecretBoundary).mockResolvedValue({
      require_approval: true,
      pending_approval_id: "d2",
    });
    vi.mocked(secretsApi.rejectApproval).mockResolvedValue({} as never);
    presence.approvePending.mockRejectedValue(new Error("cancelled"));
    renderCard();
    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    fireEvent.click(await screen.findByRole("button", { name: "Turn off" }));

    await waitFor(() => expect(secretsApi.rejectApproval).toHaveBeenCalledWith("d2"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("switch", { hidden: true })).toBeChecked();
  });

  test("cancelling the confirmation changes nothing", async () => {
    presence.available = true;
    state(true);
    renderCard();
    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    fireEvent.click(await screen.findByRole("button", { name: /cancel/i }));
    expect(secretsApi.setSecretBoundary).not.toHaveBeenCalled();
  });
});
