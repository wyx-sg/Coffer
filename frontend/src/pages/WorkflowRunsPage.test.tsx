// frontend/src/pages/WorkflowRunsPage.test.tsx
//
// The run list surface (spec workflow, FR-045). The data hook and the two
// heavy children (create dialog, table) are mocked so the test asserts this
// page's own branching — skeleton / error / empty / populated — and that both
// Create affordances open the same dialog.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { WorkflowRunsPage } from "./WorkflowRunsPage";
import { ApiError } from "@/lib/api/errors";
import type { Run } from "@/lib/api/workflow";

vi.mock("@/lib/hooks/useWorkflowRuns", () => ({
  useWorkflowRuns: vi.fn(),
  useDeleteRun: vi.fn(),
}));
vi.mock("@/components/workflow/CreateRunDialog", () => ({
  CreateRunDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="create-dialog" /> : null,
}));
vi.mock("@/components/workflow/WorkflowRunsTable", () => ({
  WorkflowRunsTable: ({ runs, isLoading }: { runs: Run[]; isLoading?: boolean }) => (
    <div data-testid="runs-table" data-loading={isLoading ? "true" : "false"}>
      {runs.map((r) => (
        <span key={r.id}>{r.title}</span>
      ))}
    </div>
  ),
}));

const { useWorkflowRuns, useDeleteRun } = await import("@/lib/hooks/useWorkflowRuns");
const useWorkflowRunsMock = vi.mocked(useWorkflowRuns);
const useDeleteRunMock = vi.mocked(useDeleteRun);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function stub(opts: { data?: Run[]; isPending?: boolean; error?: unknown }) {
  useWorkflowRunsMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof useWorkflowRuns>);
  useDeleteRunMock.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useDeleteRun>);
}

function run(id: string, title: string): Run {
  return { id, title } as Run;
}

describe("WorkflowRunsPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("keeps the header up and hands the table isLoading while the query is pending", () => {
    stub({ isPending: true });
    render(wrap(<WorkflowRunsPage />));
    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument();
    expect(screen.getByTestId("runs-table")).toHaveAttribute("data-loading", "true");
  });

  test("shows the error card with the translated message when the query errors", () => {
    stub({ error: new ApiError("BOOM", "kaboom") });
    render(wrap(<WorkflowRunsPage />));
    expect(screen.getByText("Failed to load runs")).toBeInTheDocument();
    expect(screen.getByText("kaboom")).toBeInTheDocument();
    expect(screen.queryByTestId("runs-table")).not.toBeInTheDocument();
  });

  test("the empty state explains what a run is and offers to create one", () => {
    stub({ data: [] });
    render(wrap(<WorkflowRunsPage />));
    expect(screen.queryByTestId("runs-table")).not.toBeInTheDocument();
    expect(screen.getByText(/A run is one delivery/)).toBeInTheDocument();
    // The empty state carries the only Create affordance while the list is empty.
    expect(screen.getAllByRole("button", { name: /New run/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /New run/ }));
    expect(screen.getByTestId("create-dialog")).toBeInTheDocument();
  });

  test("renders the table and the header Create button opens the dialog", () => {
    stub({ data: [run("run-1", "Ship it"), run("run-2", "Fix it")] });
    render(wrap(<WorkflowRunsPage />));
    expect(screen.getByText("Ship it")).toBeInTheDocument();
    expect(screen.getByText("Fix it")).toBeInTheDocument();
    expect(screen.queryByTestId("create-dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /New run/ }));
    expect(screen.getByTestId("create-dialog")).toBeInTheDocument();
  });
});
