// frontend/src/components/workflow/RunContext.test.tsx
// The run's one table: what it READS and what it WROTE, side by side
// (FR-032/FR-041/FR-050/FR-051). The behaviours worth pinning:
//   • both halves land in the SAME table, and a row's origin says which it is;
//   • an artifact has no unmount control, because there is nothing that would
//     mean — the catalogue is generated from disk (FR-031);
//   • a chosen file goes to its OWN route, as bytes, not as a reference —
//     mixing the two would upload a filename and mount nothing;
//   • the mount dialog and the unmount dialog both close only on SUCCESS, so a
//     refusal stays on screen with its reason rather than vanishing.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { RunContext } from "./RunContext";
import { ApiError } from "@/lib/api/errors";
import type { Artifact, RunInput } from "@/lib/api/workflow";

const listInputs = vi.fn();
const addInput = vi.fn();
const uploadInput = vi.fn();
const removeInput = vi.fn();
const listArtifacts = vi.fn();
const promoteArtifacts = vi.fn();

vi.mock("@/lib/hooks/useKnowledge", () => ({
  useKnowledgeCollections: () => ({
    data: [{ name: "product-specs", description: "Everything shipped", file_count: 4 }],
  }),
}));

vi.mock("@/lib/api/workflow", () => ({
  WORKFLOW_TEMPLATE_KIND: "workflow",
  workflowApi: {
    listInputs: (...a: unknown[]) => listInputs(...a),
    addInput: (...a: unknown[]) => addInput(...a),
    uploadInput: (...a: unknown[]) => uploadInput(...a),
    removeInput: (...a: unknown[]) => removeInput(...a),
    listArtifacts: (...a: unknown[]) => listArtifacts(...a),
    promoteArtifacts: (...a: unknown[]) => promoteArtifacts(...a),
  },
}));

const INPUTS: RunInput[] = [{ kind: "knowledge", ref: "product-specs", label: "The PRD" }];

const ARTIFACTS: Artifact[] = [
  {
    name: "td.md",
    node_key: "draft_td",
    attempt: 2,
    path: "artifacts/td.md",
    size: 4096,
    modified_at: "2026-09-17T10:26:27Z",
  },
];

function wrap(ownedHere = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        {/* A knowledge row links to the collection's own page (FR-064). */}
        <MemoryRouter>
          <RunContext runId="run-1" ownedHere={ownedHere} machine="this-machine" />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

/** Open the add dialog and pick a kind. */
async function openMount(kind?: string) {
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  const dialog = await screen.findByRole("dialog");
  if (kind !== undefined) {
    // Radix's Select opens on pointerdown, which jsdom has no event for — the
    // keyboard path is the one this repo's other Select tests take.
    fireEvent.keyDown(within(dialog).getByRole("combobox", { name: "Kind" }), { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: kind }));
  }
  return dialog;
}

describe("RunContext", () => {
  beforeEach(() => {
    listInputs.mockResolvedValue({ items: INPUTS });
    addInput.mockResolvedValue({ items: INPUTS });
    uploadInput.mockResolvedValue({ items: INPUTS });
    removeInput.mockResolvedValue({ items: [] });
    listArtifacts.mockResolvedValue({ catalogue: "", items: ARTIFACTS });
    promoteArtifacts.mockResolvedValue({ collection: "specs", copied: 1 });
  });
  afterEach(() => vi.clearAllMocks());

  test("what the run reads and what it wrote are rows of one table", async () => {
    render(wrap());

    // Mounted and produced, in one list, each saying which it is.
    const mounted = (await screen.findByText("The PRD")).closest("tr");
    expect(within(mounted!).getByText("Knowledge")).toBeInTheDocument();
    expect(within(mounted!).getByText("Added")).toBeInTheDocument();

    const produced = screen.getByText("td.md").closest("tr");
    expect(within(produced!).getByText("Artifact")).toBeInTheDocument();
    expect(within(produced!).getByText("draft_td · Attempt 2")).toBeInTheDocument();
  });

  test("an artifact offers no unmount, because there is nothing it would mean", async () => {
    render(wrap());
    await screen.findByText("td.md");

    const produced = screen.getByText("td.md").closest("tr");
    expect(within(produced!).queryByRole("button", { name: "Remove" })).toBeNull();
    // The mounted input's is there, so the absence above is about the kind of
    // row and not about the column being missing altogether.
    const mounted = screen.getByText("The PRD").closest("tr");
    expect(within(mounted!).getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  test("adds a reference through the JSON route, with its description", async () => {
    render(wrap());
    await screen.findByText("The PRD");
    // A link is the kind whose field is a text box, so it is the one that
    // exercises the JSON route; the collection picker has its own test below.
    const dialog = await openMount("Link");

    fireEvent.change(within(dialog).getByLabelText("URL"), {
      target: { value: "  https://jira/COF-2  " },
    });
    fireEvent.change(within(dialog).getByLabelText("Description (optional)"), {
      target: { value: "The ticket" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(addInput).toHaveBeenCalledWith("run-1", {
        kind: "link",
        ref: "https://jira/COF-2",
        label: "The ticket",
      }),
    );
    // Closed on success.
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("a collection is CHOSEN from the ones the vault has, never typed", async () => {
    // A typo in a free text box points the run at a collection that does not
    // exist, and nothing says so until a task goes looking for it.
    render(wrap());
    await screen.findByText("The PRD");
    const dialog = await openMount();

    fireEvent.click(within(dialog).getByRole("combobox", { name: "Collection" }));
    fireEvent.click(await screen.findByRole("option", { name: /product-specs/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(addInput).toHaveBeenCalledWith("run-1", {
        kind: "knowledge",
        ref: "product-specs",
        label: null,
      }),
    );
  });

  test("nothing chosen adds nothing", async () => {
    render(wrap());
    await screen.findByText("The PRD");
    const dialog = await openMount();

    expect(within(dialog).getByRole("button", { name: "Add" })).toBeDisabled();
    expect(addInput).not.toHaveBeenCalled();
  });

  test("the kind decides the field, and a file goes to the upload route as bytes", async () => {
    render(wrap());
    await screen.findByText("The PRD");
    const dialog = await openMount("File");

    // The picker offers File, and picking it changes the field — the old
    // form could not do this, so File was a separate button beside it.
    //
    // The real file input is hidden behind a Browse button, because the
    // browser's own control renders its label in the BROWSER's language; a
    // test cannot open a file dialog, so it drives the input the button
    // clicks. What the developer sees is the name in the field, which is
    // asserted below.
    const file = new File(["prd"], "brief.pdf", { type: "application/pdf" });
    const hidden = dialog.querySelector('input[type="file"]');
    fireEvent.change(hidden!, { target: { files: [file] } });
    expect(within(dialog).getByLabelText("File")).toHaveValue("brief.pdf");

    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));

    await waitFor(() => expect(uploadInput).toHaveBeenCalledWith("run-1", file, null));
    expect(addInput).not.toHaveBeenCalled();
  });

  test("the add dialog stays open when the add is refused", async () => {
    addInput.mockRejectedValue(new ApiError("WORKFLOW_NOT_THIS_MACHINE", "not this machine"));
    render(wrap());
    await screen.findByText("The PRD");
    const dialog = await openMount("Link");

    fireEvent.change(within(dialog).getByLabelText("URL"), {
      target: { value: "https://jira/COF-2" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));

    expect(
      await within(dialog).findByText("Another machine owns this run; it is read-only here"),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  test("the unmount dialog closes only on success", async () => {
    removeInput.mockRejectedValue(new ApiError("WORKFLOW_NOT_THIS_MACHINE", "not this machine"));
    render(wrap());
    await screen.findByText("The PRD");
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(removeInput).toHaveBeenCalledWith("run-1", "product-specs"));
    // Refused: still open, still saying why.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      await screen.findByText("Another machine owns this run; it is read-only here"),
    ).toBeInTheDocument();
  });

  test("unmounting a repository promises the source repository is untouched", async () => {
    listInputs.mockResolvedValue({
      items: [{ kind: "repo", ref: "/src/coffer", label: "Coffer" }] as RunInput[],
    });
    render(wrap());
    await screen.findByText("Coffer");
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    // The kind decides what the dialog promises: a checkout goes, the source
    // repository and its working tree do not (FR-058).
    expect(
      await screen.findByText(/its branches and its working tree — is untouched/),
    ).toBeInTheDocument();
  });

  test("says so when the run holds nothing at all rather than showing an empty table", async () => {
    listInputs.mockResolvedValue({ items: [] });
    listArtifacts.mockResolvedValue({ catalogue: "", items: [] });
    render(wrap());
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
  });

  test("a run another machine advances can be read but not added to", async () => {
    render(wrap(false));
    await screen.findByText("The PRD");

    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove" })).toBeDisabled();
  });
});
