// frontend/src/components/workflow/CreateRunDialog.test.tsx
// Creating a run asks TWO questions and no more: which template, and what is
// being delivered. The working directory is Coffer's to make, and inputs are
// mounted on the run's own page for the whole of its life (FR-050) — so both
// fields are asserted ABSENT here, not merely optional.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { CreateRunDialog } from "./CreateRunDialog";

const mutate = vi.fn();

vi.mock("@/lib/hooks/useWorkflowRuns", () => ({
  useCreateRun: () => ({ mutate, isPending: false, error: null }),
}));
const templates = vi.fn();
vi.mock("@/lib/hooks/useWorkflowTemplates", () => ({
  useWorkflowTemplates: () => ({ templates: templates() }),
}));

function wrap() {
  return (
    <MemoryRouter>
      <CreateRunDialog open onOpenChange={vi.fn()} />
    </MemoryRouter>
  );
}

describe("CreateRunDialog", () => {
  beforeEach(() => {
    mutate.mockReset();
    templates.mockReturnValue([
      { name: "delivery", enabled: true },
      { name: "hotfix", enabled: true },
    ]);
  });
  afterEach(() => vi.clearAllMocks());

  test("asks for a template and a title, and for nothing else", () => {
    render(wrap());
    expect(screen.getByLabelText("Workflow")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    // Gone: Coffer makes the directory, and inputs live on the run's page.
    expect(screen.queryByLabelText(/working directory/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /browse/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Inputs/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add input/ })).not.toBeInTheDocument();
  });

  test("cannot be submitted until both are answered, and sends exactly those two", async () => {
    render(wrap());
    const submit = screen.getByRole("button", { name: "Create run" });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "  Ship it  " } });
    // A title alone is not enough — there is no default template.
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Workflow"));
    fireEvent.click(await screen.findByRole("option", { name: "delivery" }));
    await waitFor(() => expect(submit).toBeEnabled());

    fireEvent.click(submit);
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ template: "delivery", title: "Ship it" });
  });

  test("a switched-off workflow is not offered", async () => {
    // The daemon refuses a run from a disabled workflow (FR-066), so offering
    // it here would be offering a refusal.
    templates.mockReturnValue([
      { name: "delivery", enabled: true },
      { name: "retired", enabled: false },
    ]);
    render(wrap());

    fireEvent.click(screen.getByLabelText("Workflow"));
    expect(await screen.findByRole("option", { name: "delivery" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "retired" })).toBeNull();
  });

  test("says so when every workflow is switched off, rather than showing an empty picker", () => {
    templates.mockReturnValue([{ name: "retired", enabled: false }]);
    render(wrap());

    expect(screen.getByText(/Every workflow is switched off/)).toBeInTheDocument();
  });
});
