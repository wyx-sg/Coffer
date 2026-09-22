// frontend/src/components/workflow/ApprovalCard.test.tsx
// The card's reason to exist is that the developer sees EXACTLY what will
// execute. So the first test asserts the whole payload, nested values and all,
// is on the page — not a summary, not a count of arguments, not the first
// line. If this test ever gets "simplified" to a substring check, the surface
// it guards can regress to a summary without anyone noticing.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApprovalCard } from "./ApprovalCard";
import type { Approval } from "@/lib/api/workflow";

const decideApproval = vi.fn();
vi.mock("@/lib/api/workflow", () => ({
  WORKFLOW_TEMPLATE_KIND: "workflow",
  workflowApi: {
    decideApproval: (...args: unknown[]) => decideApproval(...args),
  },
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const PAYLOAD = {
  project: "COF",
  summary: "Ship the delivery engine",
  description:
    "A long description that a summarising surface would be tempted to cut at some point well before its end, which is exactly what must not happen here.",
  labels: ["workflow", "engine"],
  fields: { assignee: "yuxing", priority: { id: "2", name: "High" } },
};

function approval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: "ap-1",
    run_id: "run-1",
    kind: "tool_call",
    tool_name: "jira__create_issue",
    status: "pending",
    payload: PAYLOAD,
    expires_at: "2026-09-17T12:00:00Z",
    created_at: "2026-09-17T11:00:00Z",
    ...overrides,
  } as Approval;
}

describe("ApprovalCard", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders the exact arguments that will execute, verbatim", () => {
    const { container } = render(wrap(<ApprovalCard approval={approval()} />));
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    // Byte-for-byte the payload, pretty-printed — nothing dropped, nothing cut.
    expect(pre?.textContent).toBe(JSON.stringify(PAYLOAD, null, 2));
    // The long description survives in full, and no elision marker was added.
    expect(pre?.textContent).toContain("exactly what must not happen here.");
    expect(pre?.textContent).not.toContain("…");
    expect(pre?.textContent).not.toMatch(/\.\.\.$/);
    // Nested structure is shown as structure, not flattened into prose.
    expect(pre?.textContent).toContain('"priority"');
    expect(pre?.textContent).toContain('"name": "High"');
  });

  test("names the tool and says when the approval expires", () => {
    render(wrap(<ApprovalCard approval={approval()} />));
    expect(screen.getByText(/jira__create_issue is waiting for approval/)).toBeInTheDocument();
    expect(screen.getByText(/Expires/)).toBeInTheDocument();
  });

  test("rejecting asks for a reason before it will go through", async () => {
    decideApproval.mockResolvedValue(approval({ status: "rejected" }));
    render(wrap(<ApprovalCard approval={approval()} />));
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    const confirm = screen
      .getAllByRole("button", { name: "Reject" })
      .find((b) => b.closest("[role=dialog]"));
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "wrong project" },
    });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm as HTMLElement);
    await waitFor(() =>
      expect(decideApproval).toHaveBeenCalledWith("ap-1", {
        decision: "rejected",
        comment: "wrong project",
        remember_tool_class: null,
      }),
    );
  });

  test("approving sends the decision, and the comment is optional", async () => {
    decideApproval.mockResolvedValue(approval({ status: "approved" }));
    render(wrap(<ApprovalCard approval={approval()} />));
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    const confirm = screen
      .getAllByRole("button", { name: "Approve" })
      .find((b) => b.closest("[role=dialog]"));
    fireEvent.click(confirm as HTMLElement);
    await waitFor(() =>
      expect(decideApproval).toHaveBeenCalledWith("ap-1", {
        decision: "approved",
        comment: null,
        remember_tool_class: null,
      }),
    );
  });

  test("a decided approval shows its state and its comment, and offers no buttons", () => {
    render(
      wrap(
        <ApprovalCard
          approval={approval({
            status: "rejected",
            decided_at: "2026-09-17T11:30:00Z",
            comment: "wrong project",
          })}
        />,
      ),
    );
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("wrong project")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });
});
