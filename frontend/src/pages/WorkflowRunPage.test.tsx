// frontend/src/pages/WorkflowRunPage.test.tsx
//
// The run page, rendered against mocked API modules rather than mocked hooks,
// so the tabs it composes are exercised for real. The behaviour worth naming
// above all others:
//
//   THE RUN'S OWN PAGE OFFERS NO CONTROLS. Every button that
//   advanced or altered a run used to live here; each one now lives on the
//   conversation of the task it belongs to. The test below names them one by
//   one, because "no controls" is only enforceable as a list.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { TooltipProvider } from "@/components/ui/tooltip";
import { WorkflowRunPage } from "./WorkflowRunPage";
import type { ArtifactList, RunDetail, RunInput } from "@/lib/api/workflow";

const getRun = vi.fn();
const listApprovals = vi.fn();
const listArtifacts = vi.fn();
const listInputs = vi.fn();

vi.mock("@/lib/api/workflow", () => ({
  WORKFLOW_TEMPLATE_KIND: "workflow",
  workflowApi: {
    getRun: (...a: unknown[]) => getRun(...a),
    listApprovals: (...a: unknown[]) => listApprovals(...a),
    listArtifacts: (...a: unknown[]) => listArtifacts(...a),
    listInputs: (...a: unknown[]) => listInputs(...a),
    addAdhocTask: vi.fn(),
    addInput: vi.fn(),
    uploadInput: vi.fn(),
    removeInput: vi.fn(),
    promoteArtifacts: vi.fn(),
    decideApproval: vi.fn(),
  },
}));

vi.mock("@/lib/api/sync", () => ({
  syncApi: {
    machines: vi.fn().mockResolvedValue({
      machines: [{ machine_id: "m-2", name: "studio-mini" }],
    }),
  },
}));

/** Every control that advances or alters a run. None may be on this page. */
const FORBIDDEN = [
  "Start",
  "Pause",
  "Resume",
  "Abort",
  "Retry",
  "Skip",
  "Complete",
  "Send feedback",
  "Restore",
  "Approve",
  "Reject",
];

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
      updated_at: "2026-09-17T10:00:00Z",
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
            status: "running",
            attempt: 2,
            allowed_actions: ["feedback", "skip"],
          },
        ],
      },
      {
        key: "build",
        name: "Build",
        nodes: [
          {
            key: "adhoc:bump-deps",
            name: "Bump the dependencies",
            type: "ai",
            status: "pending",
            attempt: 1,
            adhoc: true,
            allowed_actions: [],
          },
        ],
      },
    ],
  } as RunDetail;
}

const INPUTS: RunInput[] = [
  { kind: "knowledge", ref: "product-specs", label: "The PRD" },
  { kind: "file", ref: "uploads/brief.pdf", label: "Brief", size: 2048 },
  { kind: "link", ref: "https://jira/COF-1", label: null },
];

function wrap(entry = "/runs/run-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/runs/:runId" element={<WorkflowRunPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

describe("WorkflowRunPage", () => {
  beforeEach(() => {
    getRun.mockResolvedValue(detail());
    listApprovals.mockResolvedValue({ items: [] });
    listArtifacts.mockResolvedValue({ catalogue: "", items: [] } as ArtifactList);
    listInputs.mockResolvedValue({ items: INPUTS });
  });
  afterEach(() => vi.clearAllMocks());

  test("lists every stage and opens on the one the run is at", async () => {
    render(wrap());
    // Every stage in the rail, the same picture the template editor draws.
    expect(await screen.findByTestId("stage-design")).toBeInTheDocument();
    expect(screen.getByTestId("stage-build")).toBeInTheDocument();

    // Opened on where the run actually is, with that stage's tasks beside it.
    const node = screen.getByTestId("node-write_td");
    expect(within(node).getByText("Running")).toBeInTheDocument();
    expect(within(node).getByText("Attempt 2")).toBeInTheDocument();
    expect(screen.queryByTestId("node-adhoc:bump-deps")).not.toBeInTheDocument();
  });

  test("an unplanned task renders in its stage like any other node", async () => {
    render(wrap());
    fireEvent.click(await screen.findByTestId("stage-build"));

    const adhoc = await screen.findByTestId("node-adhoc:bump-deps");
    expect(within(adhoc).getByText("Bump the dependencies")).toBeInTheDocument();
    expect(within(adhoc).getByText("Unplanned")).toBeInTheDocument();
  });

  acceptance("workflow", "the run's own page offers no controls", async () => {
    // Everything that could possibly have put one on the page: a pending
    // approval, a node whose actions the API allowed, a run this machine owns.
    listApprovals.mockResolvedValue({
      items: [
        {
          id: "ap-1",
          run_id: "run-1",
          kind: "tool_call",
          tool_name: "jira__create_issue",
          status: "pending",
          payload: { project: "COF" },
          expires_at: "2026-09-17T12:00:00Z",
          created_at: "2026-09-17T11:00:00Z",
        },
      ],
    });
    render(wrap());
    await screen.findByTestId("stage-design");

    for (const label of FORBIDDEN) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
    // Nor the approval itself: it belongs to the task that raised it.
    expect(screen.queryByText(/waiting for approval/)).not.toBeInTheDocument();
    // Nor a conversation of the run's own.
    expect(screen.queryByRole("region", { name: /conversation/i })).not.toBeInTheDocument();
  });

  acceptance("workflow", "a task is its own conversation, opened from the run", async () => {
    render(wrap());
    const node = await screen.findByTestId("node-write_td");
    const link = within(node).getByRole("link");
    expect(link).toHaveAttribute("href", "/runs/run-1/nodes/write_td");
    // An ad-hoc task's key is URL-encoded rather than splitting the path.
    fireEvent.click(screen.getByTestId("stage-build"));
    const adhoc = await screen.findByTestId("node-adhoc:bump-deps");
    expect(within(adhoc).getByRole("link")).toHaveAttribute(
      "href",
      "/runs/run-1/nodes/adhoc%3Abump-deps",
    );
  });

  test("the context tab is addressable by URL and holds what the run reads AND wrote", async () => {
    listArtifacts.mockResolvedValue({
      catalogue: "",
      items: [
        {
          name: "td.md",
          node_key: "write_td",
          attempt: 2,
          path: "design/td.md",
          size: 2048,
          modified_at: "2026-09-17T10:00:00Z",
        },
      ],
    } as ArtifactList);
    render(wrap("/runs/run-1?tab=context"));

    // Inputs and artifacts used to be two tabs, and the whole point of merging
    // them is that one query answers "what is this run made of".
    expect(await screen.findByText("The PRD")).toBeInTheDocument();
    expect(screen.getByText("product-specs")).toBeInTheDocument();
    expect(screen.getByText("https://jira/COF-1")).toBeInTheDocument();
    expect(await screen.findByText("td.md")).toBeInTheDocument();
    expect(screen.getByText("write_td · Attempt 2")).toBeInTheDocument();
    // A file says its size; a link and a collection have none to say.
    expect(screen.getAllByText("2 KB")).toHaveLength(2);

    // Neither affordance advances the run, which is why both are allowed here
    // — mounting changes what later tasks are told, promotion copies
    // files out and leaves the run's directory as it was.
    expect(screen.getByRole("button", { name: "Add" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save to knowledge" })).toBeEnabled();
    expect(await screen.findAllByRole("button", { name: "Remove" })).toHaveLength(3);
  });

  test("a run this machine does not own cannot have its context edited, and says which machine", async () => {
    getRun.mockResolvedValue(detail({ owned_here: false, machine_id: "m-2" }));
    render(wrap("/runs/run-1?tab=context"));

    expect(
      await screen.findByText("Read-only — studio-mini advances this run"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    for (const button of await screen.findAllByRole("button", { name: "Remove" })) {
      expect(button).toBeDisabled();
    }
  });
});
