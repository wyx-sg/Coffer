// src/components/secret/PendingApprovalsSheet.test.tsx
//
// The approvals sheet the shell mounts once. It opens by itself when something
// waits, asks one question per change ("Approve a new value for …?", "Approve
// the new secret …?") with who asked, the change and what uses the secret,
// rejects over REST from any host, and — in a browser, where no presence
// check can run — shows Approve disabled, naming the app. Only the network
// boundary (`secretsApi`) and the shell module's presence seam are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { Approval, SecretRef } from "@/lib/api/secret";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { acceptance } from "@/test/acceptance";
import { PendingApprovalsSheet } from "./PendingApprovalsSheet";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    pendingApprovals: vi.fn(),
    rejectApproval: vi.fn(),
    rejectApprovals: vi.fn(),
    list: vi.fn(),
  },
}));
const approvePending = vi.fn();
const approvePendingBatch = vi.fn();
let inShell = false;
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => inShell,
  approvePending: (id: string) => approvePending(id),
  approvePendingBatch: (ids: string[]) => approvePendingBatch(ids),
  onApprovalsEvent: () => () => {},
}));

const { secretsApi } = await import("@/lib/api/secret");
const listMock = vi.mocked(secretsApi.pendingApprovals);
const rejectMock = vi.mocked(secretsApi.rejectApproval);
const secretsMock = vi.mocked(secretsApi.list);
const rejectManyMock = vi.mocked(secretsApi.rejectApprovals);

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
    target_fingerprint: null,
    decided_at: null,
    decided_by: null,
    ...over,
  };
}

const GITHUB: SecretRef = {
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
  describe("several at once", () => {
    const three = () => [
      approval({
        id: "a",
        op: "bind",
        ref: "secret/github-token",
        destination_kind: "mcp_server",
        destination_label: "alpha",
        slot: "TOKEN",
        target: "stdio alpha.sh",
      }),
      approval({
        id: "b",
        op: "bind",
        ref: "secret/github-token",
        destination_kind: "mcp_server",
        destination_label: "beta",
        slot: "TOKEN",
        target: "stdio beta.sh",
      }),
      approval({ id: "c", op: "add_secret", ref: "secret/npm-publish-token" }),
    ];
    beforeEach(() => {
      inShell = true;
      listMock.mockResolvedValue({ approvals: three() });
    });

    acceptance("secret", "approving several waits for a review of every change", async () => {
      renderSheet();
      const dialog = await screen.findByRole("dialog", { name: "3 changes waiting for approval" });
      // Nothing is ticked to begin with, so approving is a deliberate act.
      expect(within(dialog).getByRole("button", { name: /Approve selected \(0\)/ })).toBeDisabled();
      fireEvent.click(within(dialog).getByRole("checkbox", { name: /Select all/ }));
      fireEvent.click(within(dialog).getByRole("button", { name: /Approve selected \(3\)/ }));

      // The review lists every change the one confirmation covers; nothing ran yet.
      const review = await screen.findByRole("dialog", { name: "Approve these 3 changes?" });
      const rows = within(review).getAllByTestId("batch-review-row");
      expect(rows).toHaveLength(3);
      expect(rows[0]).toHaveTextContent("alpha");
      expect(rows[0]).toHaveTextContent("stdio alpha.sh");
      expect(rows[1]).toHaveTextContent("beta");
      expect(rows[2]).toHaveTextContent("Approve the new secret npm-publish-token?");
      expect(approvePendingBatch).not.toHaveBeenCalled();
      expect(approvePending).not.toHaveBeenCalled();
    });

    test("one confirmation approves exactly the ticked changes and each outcome is shown", async () => {
      approvePendingBatch.mockResolvedValue({
        results: [
          { id: "a", outcome: "approved", reason: null, approval: null },
          { id: "c", outcome: "skipped", reason: "changed", approval: null },
        ],
      });
      renderSheet();
      const dialog = await screen.findByRole("dialog");
      fireEvent.click(within(dialog).getAllByRole("checkbox", { name: /^Select (?!all)/ })[0]);
      fireEvent.click(within(dialog).getAllByRole("checkbox", { name: /^Select (?!all)/ })[2]);
      fireEvent.click(within(dialog).getByRole("button", { name: /Approve selected \(2\)/ }));
      const review = await screen.findByRole("dialog", { name: "Approve these 2 changes?" });
      fireEvent.click(within(review).getByRole("button", { name: "Approve all 2…" }));

      await waitFor(() => expect(approvePendingBatch).toHaveBeenCalledTimes(1));
      expect(approvePendingBatch).toHaveBeenCalledWith(["a", "c"]);
      const done = await screen.findByRole("dialog", { name: "Approval finished" });
      const rows = within(done).getAllByTestId("batch-review-row");
      expect(rows[0]).toHaveTextContent("Approved");
      expect(rows[1]).toHaveTextContent("it changed after you looked");
    });

    test("backing out of the review approves nothing", async () => {
      renderSheet();
      const dialog = await screen.findByRole("dialog");
      fireEvent.click(within(dialog).getByRole("checkbox", { name: /Select all/ }));
      fireEvent.click(within(dialog).getByRole("button", { name: /Approve selected/ }));
      const review = await screen.findByRole("dialog", { name: "Approve these 3 changes?" });
      fireEvent.click(within(review).getByRole("button", { name: "Back" }));
      expect(
        await screen.findByRole("dialog", { name: "3 changes waiting for approval" }),
      ).toBeInTheDocument();
      expect(approvePendingBatch).not.toHaveBeenCalled();
    });

    test("in a browser Approve selected is disabled but Reject selected works", async () => {
      inShell = false;
      rejectManyMock.mockResolvedValue({
        results: [{ id: "b", outcome: "rejected", reason: null, approval: null }],
      });
      renderSheet();
      const dialog = await screen.findByRole("dialog");
      fireEvent.click(within(dialog).getAllByRole("checkbox", { name: /^Select (?!all)/ })[1]);
      expect(within(dialog).getByRole("button", { name: /Approve selected \(1\)/ })).toBeDisabled();
      fireEvent.click(within(dialog).getByRole("button", { name: /Reject selected \(1\)/ }));
      await waitFor(() => expect(rejectManyMock).toHaveBeenCalledWith(["b"]));
      expect(approvePendingBatch).not.toHaveBeenCalled();
    });

    test("a single waiting change has no selection controls", async () => {
      listMock.mockResolvedValue({ approvals: [approval()] });
      renderSheet();
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).queryByTestId("approvals-batch-bar")).not.toBeInTheDocument();
      expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument();
    });
  });
});
