// frontend/src/pages/WorkflowNodePage.test.tsx
//
// The task's conversation page — where a run is driven now (FR-030/FR-052).
// Two behaviours are load-bearing:
//
//   • A PENDING APPROVAL RENDERS ITS ARGUMENTS VERBATIM. Byte-for-byte what
//     will execute, no summary and no ellipsis. If this ever gets "simplified"
//     to a substring check, the surface it guards can regress to a summary
//     without anyone noticing, and the developer would be approving something
//     they cannot see.
//   • A task that has never started says so, rather than showing an empty
//     thread that reads like a conversation in which nothing was said.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { TooltipProvider } from "@/components/ui/tooltip";
import { WorkflowNodePage } from "./WorkflowNodePage";
import type { Approval, RunDetail } from "@/lib/api/workflow";

const getRun = vi.fn();
const listApprovals = vi.fn();
const sayToNode = vi.fn();

vi.mock("@/lib/api/workflow", () => ({
  WORKFLOW_TEMPLATE_KIND: "workflow",
  workflowApi: {
    getRun: (...a: unknown[]) => getRun(...a),
    listApprovals: (...a: unknown[]) => listApprovals(...a),
    decideApproval: vi.fn(),
    sayToNode: (...a: unknown[]) => sayToNode(...a),
  },
}));

const sendMessage = vi.fn().mockResolvedValue({ queued: true });

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listMessages: vi.fn().mockResolvedValue({ messages: [] }),
    sendMessage: (...a: unknown[]) => sendMessage(...a),
    setPending: vi.fn().mockResolvedValue({ pending: [] }),
    interruptTurn: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("@/lib/chat/streamClient", () => ({
  // The persistent GET /events subscription — an async generator that ends
  // immediately, so no turn is in flight in these page-level tests.
  subscribeConversationEvents: vi.fn(async function* () {}),
}));

vi.mock("@/lib/api/sync", () => ({
  syncApi: {
    machines: vi.fn().mockResolvedValue({
      machines: [{ machine_id: "m-2", name: "studio-mini" }],
    }),
  },
}));

// Nested objects, a list and a long string: everything a summarising surface
// would be tempted to fold away.
const PAYLOAD = {
  project: "COF",
  summary: "Ship the delivery engine",
  description:
    "A long description that a summarising surface would be tempted to cut at some point well before its end, which is exactly what must not happen here.",
  labels: ["workflow", "engine"],
  fields: { assignee: "yuxing", priority: { id: "2", name: "High" } },
};

function detail(overrides: Partial<RunDetail["run"]> = {}): RunDetail {
  return {
    run: {
      id: "run-1",
      title: "Ship the delivery engine",
      template_ref: "delivery",
      status: "running",
      version: 4,
      workdir: "/repo",
      machine_id: "m-1",
      owned_here: true,
      current_stage_key: "design",
      current_node_key: "write_td",
      created_at: "2026-09-17T09:00:00Z",
      ...overrides,
    },
    stages: [
      {
        key: "design",
        name: "Design",
        nodes: [
          {
            key: "write_td",
            name: "Write the TD",
            type: "ai",
            skill: "coffer-writing-td",
            status: "running",
            attempt: 2,
            allowed_actions: ["feedback", "skip"],
            latest: {
              id: "att-2",
              node_key: "write_td",
              stage_key: "design",
              attempt: 2,
              status: "running",
              conversation_id: "conv-td",
              started_at: "2026-09-17T09:30:00Z",
            },
          },
          {
            key: "review_td",
            name: "Review the TD",
            type: "manual",
            status: "pending",
            attempt: 1,
            allowed_actions: ["start"],
          },
        ],
      },
    ],
  } as RunDetail;
}

function approval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: "ap-1",
    run_id: "run-1",
    attempt_id: "att-2",
    kind: "tool_call",
    tool_name: "jira__create_issue",
    status: "pending",
    payload: PAYLOAD,
    expires_at: "2026-09-17T12:00:00Z",
    created_at: "2026-09-17T11:00:00Z",
    ...overrides,
  } as Approval;
}

function wrap(entry = "/runs/run-1/nodes/write_td") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/runs/:runId/nodes/:nodeKey" element={<WorkflowNodePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

describe("WorkflowNodePage", () => {
  beforeEach(() => {
    getRun.mockResolvedValue(detail());
    listApprovals.mockResolvedValue({ items: [] });
    sayToNode.mockResolvedValue({
      id: "att-3",
      node_key: "review_td",
      stage_key: "design",
      attempt: 1,
      status: "pending",
    });
  });
  afterEach(() => vi.clearAllMocks());

  test("shows the task, its stage, its status and its own conversation", async () => {
    render(wrap());
    expect(await screen.findByRole("heading", { name: "Write the TD" })).toBeInTheDocument();
    expect(screen.getByText(/Ship the delivery engine · Design · AI/)).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Attempt 2")).toBeInTheDocument();
    expect(screen.getByText("coffer-writing-td")).toBeInTheDocument();
    // The thread, with a composer — typing here is how the task is steered.
    expect(await screen.findByRole("region", { name: "Task conversation" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message input" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  acceptance("workflow", "a task is driven by talking to it, not by buttons", async () => {
    render(wrap());
    await screen.findByRole("heading", { name: "Write the TD" });

    // Not one of them, however the API described this node's allowed actions.
    // "Send back" is in the list because the header carried it longest: a
    // workflow draws no route between stages now (FR-025), so acting on a
    // finding is retrying a task or adding one, both of which are sentences.
    for (const label of [
      "Start",
      "Retry",
      "Skip",
      "Complete",
      "Send feedback",
      "Send back",
      "Restore",
    ]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
    // What replaced them: the composer, in the task's own conversation.
    expect(screen.getByRole("textbox", { name: "Message input" })).toBeInTheDocument();
  });

  test("a pending approval renders the arguments VERBATIM, with Approve and Reject", async () => {
    listApprovals.mockResolvedValue({ items: [approval()] });
    const { container } = render(wrap());
    const thread = await screen.findByRole("region", { name: "Task conversation" });
    // IN the conversation, under the message that led to it — not a banner
    // over the page (FR-039).
    expect(
      await within(thread).findByText(/jira__create_issue is waiting for approval/),
    ).toBeInTheDocument();

    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    // Byte-for-byte what will execute: nothing dropped, nothing reordered.
    expect(pre?.textContent).toBe(JSON.stringify(PAYLOAD, null, 2));
    // And no elision of any kind crept in.
    expect(pre?.textContent).toContain("exactly what must not happen here.");
    expect(pre?.textContent).not.toMatch(/…|\.\.\./);

    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  test("an approval raised by a different attempt stays off this page", async () => {
    listApprovals.mockResolvedValue({ items: [approval({ attempt_id: "att-other" })] });
    render(wrap());
    await screen.findByRole("heading", { name: "Write the TD" });
    expect(screen.queryByText(/waiting for approval/)).not.toBeInTheDocument();
  });

  test("a task that has never started says so rather than showing an empty thread", async () => {
    render(wrap("/runs/run-1/nodes/review_td"));
    expect(await screen.findByText("This task has not started")).toBeInTheDocument();
    expect(screen.getByText(/What you write below becomes its brief/)).toBeInTheDocument();
    // No transcript — nobody has spoken. The brief panel is what is there.
    expect(screen.queryByRole("region", { name: "Task conversation" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Task brief" })).toBeInTheDocument();
  });

  test("a task that has not started can still be told what to do", async () => {
    render(wrap("/runs/run-1/nodes/review_td"));
    await screen.findByRole("region", { name: "Task brief" });

    fireEvent.change(screen.getByRole("textbox", { name: "Message input" }), {
      target: { value: "use the 0088 migration style" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() =>
      expect(sayToNode).toHaveBeenCalledWith("run-1", "review_td", "use the 0088 migration style"),
    );
  });

  test("a running task's sentence goes to its conversation, not to the engine", async () => {
    render(wrap());
    await screen.findByRole("region", { name: "Task conversation" });

    fireEvent.change(screen.getByRole("textbox", { name: "Message input" }), {
      target: { value: "stop and check the fixtures" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    // The agent is reading that conversation right now and the message queues
    // there; routing it through the engine would be a second way to say it.
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    expect(sendMessage.mock.calls[0][0]).toBe("conv-td");
    expect(sayToNode).not.toHaveBeenCalled();
  });

  test("a node key this run does not have is reported, not rendered blank", async () => {
    render(wrap("/runs/run-1/nodes/nope"));
    expect(await screen.findByText("This task is not part of this run")).toBeInTheDocument();
  });

  test("a run another machine advances is read-only here", async () => {
    getRun.mockResolvedValue(detail({ owned_here: false, machine_id: "m-2" }));
    render(wrap());
    expect(await screen.findByRole("region", { name: "Task conversation" })).toBeInTheDocument();
    expect(screen.getByText(/this conversation is read-only here/)).toBeInTheDocument();
  });
});
