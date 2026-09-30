// src/components/credentials/PendingApprovalsSheet.test.tsx
//
// The approvals sheet the shell mounts once. It opens by itself when something
// waits, asks one question per change ("Approve a new value for …?", "Approve
// the new secret …?") with who asked, the change and what uses the secret,
// rejects over REST from any host, and — in a browser, where no presence
// check can run — shows Approve disabled, naming the app. Only the network
// boundary (`credentialsApi`) and the shell module's presence seam are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { Approval, CredentialRef } from "@/lib/api/credentials";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { acceptance } from "@/test/acceptance";
import { PendingApprovalsSheet } from "./PendingApprovalsSheet";

vi.mock("@/lib/api/credentials", () => ({
  credentialsApi: { pendingApprovals: vi.fn(), rejectApproval: vi.fn(), list: vi.fn() },
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
const secretsMock = vi.mocked(credentialsApi.list);

function approval(over: Partial<Approval> = {}): Approval {
  return {
    id: "apr-1",
    op: "replace_value",
    status: "pending",
    description: "replace the value of secret 'secret/github-token'",
    created_at: "2026-09-30T08:00:00Z",
    requested_by: "cli",
    ref: "secret/github-token",
    destination_kind: null,
    destination_label: null,
    destination_uid: null,
    slot: null,
    target: null,
    decided_at: null,
    decided_by: null,
    ...over,
  };
}

const GITHUB: CredentialRef = {
  ref: "secret/github-token",
  uri: "coffer://secret/github-token",
  present: true,
  locked: false,
  created_at: "2026-08-12T09:00:00Z",
  last_used_at: null,
  cited_by: [{ kind: "mcp_server", name: "github", uid: "u-gh" }],
  mentioned_by_skills: ["release-notes"],
  unreferenced: false,
  bindings: [],
  readable_by_local_processes: true,
};

function renderSheet() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <PendingApprovalsSheet />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  inShell = false;
  listMock.mockResolvedValue({ approvals: [approval()] });
  secretsMock.mockResolvedValue({ refs: [GITHUB] });
  rejectMock.mockResolvedValue(approval({ status: "rejected" }));
});
afterEach(() => vi.clearAllMocks());

describe("PendingApprovalsSheet", () => {
  test("stays closed while nothing waits", async () => {
    listMock.mockResolvedValue({ approvals: [] });
    renderSheet();
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(secretsMock).not.toHaveBeenCalled();
  });

  test("a new value asks its question with who asked and what uses the secret", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog", {
      name: "Approve a new value for github-token?",
    });
    const row = within(dialog).getByTestId("approval-row");
    expect(row).toHaveTextContent("New value");
    expect(row).toHaveTextContent("You · on the command line");
    await waitFor(() => expect(row).toHaveTextContent("MCP server github, Skill release-notes"));
    expect(row).toHaveTextContent("keep using the current value");
  });

  acceptance("secret", "adding a standalone secret waits for approval", async () => {
    listMock.mockResolvedValue({
      approvals: [approval({ op: "add_secret", ref: "secret/npm-publish-token" })],
    });
    renderSheet();
    const dialog = await screen.findByRole("dialog", {
      name: "Approve the new secret npm-publish-token?",
    });
    const row = within(dialog).getByTestId("approval-row");
    expect(row).toHaveTextContent("New secret");
    expect(row).toHaveTextContent("Nothing yet");
    expect(row).toHaveTextContent("It can be used only after you approve it.");
  });

  test("several waiting changes are counted, each as its own question", async () => {
    listMock.mockResolvedValue({
      approvals: [
        approval(),
        approval({ id: "apr-2", op: "add_secret", ref: "secret/npm-publish-token" }),
      ],
    });
    renderSheet();
    const dialog = await screen.findByRole("dialog", { name: "2 changes waiting for approval" });
    expect(dialog).toHaveTextContent("Approve the new secret npm-publish-token?");
    expect(within(dialog).getAllByTestId("approval-row")).toHaveLength(2);
  });

  test("a dismissed sheet comes back when Review asks for it", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    act(() => openApprovalsSheet());
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  test("reject calls the route, from any host", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^reject$/i }));
    await waitFor(() => expect(rejectMock).toHaveBeenCalledWith("apr-1"));
  });

  acceptance("secret", "a browser can reject a change but not approve it", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    const approve = within(dialog).getByRole("button", { name: /^approve$/i });
    expect(approve).toBeDisabled();
    expect(approve.parentElement).toHaveAttribute("title", "Approve in the Coffer desktop app");
    expect(dialog).toHaveTextContent("Open the Coffer app on this Mac to approve");
    expect(within(dialog).getByRole("button", { name: /^reject$/i })).toBeEnabled();
    expect(approvePending).not.toHaveBeenCalled();
  });

  test("in the desktop app, Approve… runs through the shell's presence check", async () => {
    inShell = true;
    approvePending.mockResolvedValue(approval({ status: "approved" }));
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Approving asks for Touch ID or your login password.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve…" }));
    await waitFor(() => expect(approvePending).toHaveBeenCalledWith("apr-1"));
  });

  test("closing dismisses what it showed", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /close/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
