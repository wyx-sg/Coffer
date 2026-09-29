// src/components/credentials/PendingApprovalsSheet.test.tsx
//
// The approvals sheet the shell mounts once. It opens by itself when something
// waits, says who asked for what, rejects over REST from any host, and — in a
// browser, where no presence check can run — offers "Open in Coffer app" in
// Approve's place. Only the network boundary (`credentialsApi`) and the shell
// module's presence seam are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { Approval } from "@/lib/api/credentials";
import { PendingApprovalsSheet } from "./PendingApprovalsSheet";

vi.mock("@/lib/api/credentials", () => ({
  credentialsApi: { pendingApprovals: vi.fn(), rejectApproval: vi.fn() },
}));
const approvePending = vi.fn();
let inShell = false;
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => inShell,
  approvePending: (id: string) => approvePending(id),
  onApprovalsEvent: () => () => {},
}));

const { credentialsApi } = await import("@/lib/api/credentials");
const listMock = vi.mocked(credentialsApi.pendingApprovals);
const rejectMock = vi.mocked(credentialsApi.rejectApproval);

function approval(over: Partial<Approval> = {}): Approval {
  return {
    id: "apr-1",
    op: "replace_value",
    status: "pending",
    description: "Replace the value of GITHUB_TOKEN used by github",
    created_at: "2026-09-30T08:00:00Z",
    requested_by: "cli",
    ref: "mcp_server/0123/GITHUB_TOKEN",
    destination_kind: "mcp_server",
    destination_label: "github",
    destination_uid: "u-github",
    slot: "GITHUB_TOKEN",
    target: null,
    decided_at: null,
    decided_by: null,
    ...over,
  };
}

function renderSheet() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <PendingApprovalsSheet />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  inShell = false;
  listMock.mockResolvedValue({ approvals: [approval()] });
  rejectMock.mockResolvedValue(approval({ status: "rejected" }));
});
afterEach(() => vi.clearAllMocks());

describe("PendingApprovalsSheet", () => {
  test("stays closed while nothing waits", async () => {
    listMock.mockResolvedValue({ approvals: [] });
    renderSheet();
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("opens by itself and says who asked, which secret, and where it goes", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/1 change waiting for approval/i);
    const row = within(dialog).getByTestId("approval-row");
    expect(row).toHaveTextContent("Replace the value of GITHUB_TOKEN used by github");
    expect(row).toHaveTextContent("cli");
    expect(row).toHaveTextContent("mcp_server/0123/GITHUB_TOKEN");
    expect(row).toHaveTextContent("mcp_server · github (GITHUB_TOKEN)");
  });

  test("reject calls the route, from any host", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^reject$/i }));
    await waitFor(() => expect(rejectMock).toHaveBeenCalledWith("apr-1"));
  });

  test("in a browser, Approve is replaced by Open in Coffer app", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /open in coffer app/i })).toBeDisabled();
    expect(approvePending).not.toHaveBeenCalled();
  });

  test("in the desktop app, Approve runs through the shell", async () => {
    inShell = true;
    approvePending.mockResolvedValue(approval({ status: "approved" }));
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^approve$/i }));
    await waitFor(() => expect(approvePending).toHaveBeenCalledWith("apr-1"));
  });

  test("closing dismisses what it showed", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /close/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
