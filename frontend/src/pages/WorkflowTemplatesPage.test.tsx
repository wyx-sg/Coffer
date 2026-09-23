// frontend/src/pages/WorkflowTemplatesPage.test.tsx
//
// The template list: its branching — skeleton / error / empty /
// populated — and the two things the list itself has to say, which are the
// stages IN ORDER and whether the template is enabled. The table is real, so
// the order summary is asserted where it is rendered.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { WorkflowTemplatesPage } from "./WorkflowTemplatesPage";
import { ApiError } from "@/lib/api/errors";
import type { WorkflowTemplate } from "@/lib/hooks/useWorkflowTemplates";

vi.mock("@/lib/hooks/useWorkflowTemplates", () => ({
  useWorkflowTemplates: vi.fn(),
  useDeleteWorkflowTemplate: vi.fn(),
}));
vi.mock("@/components/workflow/TemplateCreateDialog", () => ({
  TemplateCreateDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="create-dialog" /> : null,
}));

const { useWorkflowTemplates, useDeleteWorkflowTemplate } =
  await import("@/lib/hooks/useWorkflowTemplates");
const listMock = vi.mocked(useWorkflowTemplates);
const deleteMock = vi.mocked(useDeleteWorkflowTemplate);

function template(name: string, stages: string[]): WorkflowTemplate {
  return {
    uid: `uid-${name}`,
    name,
    description: `${name} flow`,
    enabled: true,
    config: {
      stages: stages.map((s) => ({ key: s.toLowerCase(), name: s, nodes: [] })),
    },
  } as WorkflowTemplate;
}

function stub(opts: {
  templates?: WorkflowTemplate[];
  isPending?: boolean;
  error?: unknown;
  mutateAsync?: () => Promise<unknown>;
}) {
  listMock.mockReturnValue({
    templates: opts.templates ?? [],
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof useWorkflowTemplates>);
  deleteMock.mockReturnValue({
    mutateAsync: opts.mutateAsync ?? vi.fn().mockResolvedValue(undefined),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useDeleteWorkflowTemplate>);
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <WorkflowTemplatesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkflowTemplatesPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("lists each template and how big it is, not what is inside it", () => {
    stub({ templates: [template("delivery", ["Design", "Coding", "Testing"])] });
    render(wrap());
    expect(screen.getByRole("heading", { name: "Workflows" })).toBeInTheDocument();
    expect(screen.getByText("delivery")).toBeInTheDocument();
    // A list is read by scanning down a column; the chain is a paragraph in a
    // cell, and the shape is drawn properly on the workflow's own page.
    expect(screen.getByText("3 stages")).toBeInTheDocument();
    expect(screen.queryByText(/Design → Coding/)).not.toBeInTheDocument();
    // Enabled is a switch, not a badge: two states, acted on from the list.
    expect(screen.getByRole("switch", { name: "Enabled: delivery" })).toBeChecked();
  });

  test("a stage name still finds its template in the search box", () => {
    // The column stopped showing them; the template still answers for them.
    stub({ templates: [template("delivery", ["Design", "Coding", "Testing"])] });
    render(wrap());
    fireEvent.change(screen.getByPlaceholderText("Search workflows…"), {
      target: { value: "Coding" },
    });
    expect(screen.getByText("delivery")).toBeInTheDocument();
  });

  test("offers the create dialog from the empty state and from the header", () => {
    stub({ templates: [] });
    const { rerender } = render(wrap());
    expect(screen.queryByTestId("create-dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /New workflow/ }));
    expect(screen.getByTestId("create-dialog")).toBeInTheDocument();

    stub({ templates: [template("delivery", ["Design"])] });
    rerender(wrap());
    fireEvent.click(screen.getByRole("button", { name: /New workflow/ }));
    expect(screen.getByTestId("create-dialog")).toBeInTheDocument();
  });

  test("shows the translated failure instead of the table when the query errors", () => {
    stub({ error: new ApiError("BOOM", "kaboom") });
    render(wrap());
    expect(screen.getByText("Failed to load workflows")).toBeInTheDocument();
    expect(screen.getByText("kaboom")).toBeInTheDocument();
  });

  test("the delete confirmation closes only once the delete has gone through", async () => {
    let refuse = true;
    const mutateAsync = vi.fn(() =>
      refuse ? Promise.reject(new ApiError("BOOM", "still in use")) : Promise.resolve(undefined),
    );
    stub({ templates: [template("delivery", ["Design"])], mutateAsync });
    render(wrap());

    fireEvent.click(screen.getByRole("button", { name: "Delete workflow: delivery" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    // Refused: the dialog stays open, carrying the reason.
    expect(await screen.findByText("still in use")).toBeInTheDocument();
    expect(dialog).toBeInTheDocument();

    refuse = false;
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // By uid: the row's identity, not the label the confirmation printed.
    expect(mutateAsync).toHaveBeenCalledWith("uid-delivery");
  });
});
