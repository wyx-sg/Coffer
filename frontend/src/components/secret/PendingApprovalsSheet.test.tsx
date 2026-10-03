// src/components/secret/PendingApprovalsSheet.test.tsx
//
// The approvals dialog the shell mounts once. It opens by itself when something waits, lists every
// change in one 1060-wide table (Change · Secret · Goes to · Requested by · At) with a header box
// that selects them all, rejects over REST from any host, and — in a browser, where no presence
// check can run — shows Approve disabled, naming the app. Approving several runs one presence
// check over the ticked list and turns the same dialog into a per-change result. Only the network
// boundary (`secretsApi`) and the shell module's presence seam are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
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
      <ToastProvider>
        <TooltipProvider>
          <PendingApprovalsSheet />
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  inShell = false;
  listMock.mockResolvedValue({ approvals: [approval()] });
  secretsMock.mockResolvedValue({ refs: [GITHUB] });
  rejectManyMock.mockResolvedValue({
    results: [{ id: "apr-1", outcome: "rejected", reason: null, approval: null }],
  });
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

  test("one waiting change is a table row with who asked and what uses the secret", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog", { name: "1 change waiting for approval" });
    const row = within(dialog).getByTestId("approval-row");
    expect(row).toHaveTextContent("New value");
    expect(row).toHaveTextContent("github-token");
    expect(row).toHaveTextContent("You · on the command line");
    await waitFor(() => expect(row).toHaveTextContent("Used by github, release-notes"));
    for (const head of ["Change", "Secret", "Goes to", "Requested by", "At"]) {
      expect(within(dialog).getByRole("columnheader", { name: head })).toBeInTheDocument();
    }
  });

  acceptance("secret", "adding a standalone secret waits for approval", async () => {
    listMock.mockResolvedValue({
      approvals: [approval({ op: "add_secret", ref: "secret/npm-publish-token" })],
    });
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    const row = within(dialog).getByTestId("approval-row");
    expect(row).toHaveTextContent("New secret");
    expect(row).toHaveTextContent("npm-publish-token");
    expect(row).toHaveTextContent("Nothing yet");
  });

  test("a change sent somewhere says where, with the slot and the target", async () => {
    listMock.mockResolvedValue({
      approvals: [
        approval({
          op: "bind",
          destination_kind: "mcp_server",
          destination_label: "filesystem-plus",
          slot: "OPENAI_API_KEY",
          target: "stdio fs.sh",
        }),
      ],
    });
    renderSheet();
    const row = await screen.findByTestId("approval-row");
    expect(row).toHaveTextContent("New use");
    expect(row).toHaveTextContent("Sent to MCP server filesystem-plus (OPENAI_API_KEY)");
    expect(row).toHaveTextContent("stdio fs.sh");
  });

  test("a dismissed dialog comes back when Review asks for it", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    act(() => openApprovalsSheet());
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  test("closing dismisses what it showed", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /close/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("reject calls the route from any host, and the toast says the secret keeps its value", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(rejectManyMock).toHaveBeenCalledWith(["apr-1"]));
    expect(
      await screen.findByText("Rejected · github-token keeps its current value"),
    ).toBeInTheDocument();
  });

  acceptance("secret", "a browser can reject a change but not approve it", async () => {
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    const approve = within(dialog).getByRole("button", { name: "Approve…" });
    expect(approve).toBeDisabled();
    expect(approve.parentElement).toHaveAttribute("title", "Approve in the Coffer desktop app");
    expect(dialog).toHaveTextContent("approve it in the Coffer desktop app");
    expect(within(dialog).getByRole("button", { name: "Reject" })).toBeEnabled();
    expect(approvePending).not.toHaveBeenCalled();
  });

  test("in the desktop app, Approve… runs through the shell's presence check", async () => {
    inShell = true;
    approvePending.mockResolvedValue(approval({ status: "approved" }));
    renderSheet();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Approving asks for Touch ID or your login password once.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve…" }));
    await waitFor(() => expect(approvePending).toHaveBeenCalledWith("apr-1"));
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
      // The table is the review: every change, where it goes and the target that receives it.
      const rows = within(dialog).getAllByTestId("approval-row");
      expect(rows).toHaveLength(3);
      expect(rows[0]).toHaveTextContent("alpha");
      expect(rows[0]).toHaveTextContent("stdio alpha.sh");
      expect(rows[1]).toHaveTextContent("beta");
      expect(rows[2]).toHaveTextContent("npm-publish-token");
      // Nothing is ticked to begin with; the buttons then answer all, and nothing ran yet.
      expect(within(dialog).getByText("Select changes to answer some of them")).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Reject all" })).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Approve all 3…" })).toBeEnabled();
      fireEvent.click(within(dialog).getByRole("checkbox", { name: "Select all changes" }));
      expect(within(dialog).getByText("3 of 3 selected")).toBeInTheDocument();
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
      const boxes = within(dialog).getAllByRole("checkbox", { name: /^Select (?!all)/ });
      fireEvent.click(boxes[0]);
      fireEvent.click(boxes[2]);
      expect(within(dialog).getByText("2 of 3 selected")).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Reject 2" })).toBeInTheDocument();
      fireEvent.click(within(dialog).getByRole("button", { name: "Approve 2…" }));

      await waitFor(() => expect(approvePendingBatch).toHaveBeenCalledTimes(1));
      expect(approvePendingBatch).toHaveBeenCalledWith(["a", "c"]);
      const done = await screen.findByRole("dialog", { name: "Approved 1 of 2 changes" });
      const rows = within(done).getAllByTestId("batch-review-row");
      expect(rows[0]).toHaveTextContent("Approved");
      expect(rows[1]).toHaveTextContent("Skipped");
      expect(rows[1]).toHaveTextContent("It changed after you looked; it is still waiting.");
      expect(done).toHaveTextContent("Every change is recorded in Activity.");
      fireEvent.click(within(done).getByRole("button", { name: "Done" }));
      expect(
        await screen.findByRole("dialog", { name: "3 changes waiting for approval" }),
      ).toBeInTheDocument();
    });

    test("in a browser Approve is disabled but Reject N works", async () => {
      inShell = false;
      rejectManyMock.mockResolvedValue({
        results: [{ id: "b", outcome: "rejected", reason: null, approval: null }],
      });
      renderSheet();
      const dialog = await screen.findByRole("dialog");
      expect(dialog).toHaveTextContent("You can reject from here.");
      fireEvent.click(within(dialog).getAllByRole("checkbox", { name: /^Select (?!all)/ })[1]);
      expect(within(dialog).getByRole("button", { name: "Approve 1…" })).toBeDisabled();
      fireEvent.click(within(dialog).getByRole("button", { name: "Reject 1" }));
      await waitFor(() => expect(rejectManyMock).toHaveBeenCalledWith(["b"]));
      expect(approvePendingBatch).not.toHaveBeenCalled();
    });
  });
});
