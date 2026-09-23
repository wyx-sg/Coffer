// frontend/src/components/workflow/WorkflowRunsTable.test.tsx
// The list row has to answer four questions without opening the run: what is
// it, where did it get to, when did it last move, and which machine is
// advancing it.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { WorkflowRunsTable } from "./WorkflowRunsTable";
import type { Run } from "@/lib/api/workflow";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

vi.mock("@/lib/api/sync", () => ({
  syncApi: {
    machines: vi.fn().mockResolvedValue({
      machines: [{ machine_id: "m-2", name: "studio-mini" }],
    }),
  },
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function run(overrides: Partial<Run> = {}): Run {
  return {
    id: "run-1",
    title: "Ship the delivery engine",
    template_ref: "delivery",
    status: "running",
    version: 3,
    workdir: "/repo",
    machine_id: "m-1",
    owned_here: true,
    current_stage_key: "design",
    current_stage_name: "Tech Design",
    current_node_key: "write_td",
    created_at: "2026-09-17T09:00:00Z",
    updated_at: "2026-09-17T10:00:00Z",
    ...overrides,
  } as Run;
}

describe("WorkflowRunsTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("a row says what it is, its template, its status and where it got to", () => {
    render(wrap(<WorkflowRunsTable runs={[run()]} onDelete={vi.fn()} />));
    expect(screen.getByText("Ship the delivery engine")).toBeInTheDocument();
    expect(screen.getByText("delivery")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    // Where it is, is ONE stage — read down the column, not reassembled per
    // row — and it is what the developer called it, never the key.
    expect(screen.getByText("Tech Design")).toBeInTheDocument();
    expect(screen.queryByText(/design → write_td/)).not.toBeInTheDocument();
    expect(screen.queryByText("write_td")).not.toBeInTheDocument();
  });

  test("a run whose frozen template no longer names its stage falls back to the key", () => {
    // The snapshot is the only place that still knows what the stage was
    // called; a run whose one is unreadable still has to say where it is.
    render(
      wrap(<WorkflowRunsTable runs={[run({ current_stage_name: null })]} onDelete={vi.fn()} />),
    );
    expect(screen.getByText("design")).toBeInTheDocument();
  });

  test("a run owned here and one owned elsewhere are told apart by name", async () => {
    render(
      wrap(
        <WorkflowRunsTable
          runs={[run(), run({ id: "run-2", title: "Other", owned_here: false, machine_id: "m-2" })]}
          onDelete={vi.fn()}
        />,
      ),
    );
    expect(screen.getByText("This machine")).toBeInTheDocument();
    expect(await screen.findByText("studio-mini")).toBeInTheDocument();
  });

  test("clicking a row opens the run; deleting it does not", () => {
    const onDelete = vi.fn();
    render(wrap(<WorkflowRunsTable runs={[run()]} onDelete={onDelete} />));
    fireEvent.click(screen.getByText("Ship the delivery engine"));
    expect(navigate).toHaveBeenCalledWith("/runs/run-1");

    navigate.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /Delete run: Ship the delivery engine/ }));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(navigate).not.toHaveBeenCalled();
  });
});
