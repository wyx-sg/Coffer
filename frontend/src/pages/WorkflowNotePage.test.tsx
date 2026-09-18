// frontend/src/pages/WorkflowNotePage.test.tsx
//
// The one thing in a run's context the developer WROTE (FR-069). Two things
// are load-bearing here and neither is the markdown:
//
//   • THE REWRITE KEEPS THE REF. A note is known to every task by the name it
//     had when they read the run's inputs, so a save that renamed the file
//     would break the reference to make room for itself.
//   • AN IMAGE IS FETCHED, NOT LINKED. The daemon authorises by header and an
//     <img> cannot send one, so a relative src has to become an object URL or
//     the screenshot renders as a broken image for everyone.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { WorkflowNotePage } from "./WorkflowNotePage";

const readFile = vi.fn();
const listInputs = vi.fn();
const rewriteNote = vi.fn();
const readFileBytes = vi.fn();

vi.mock("@/lib/api/workflow", () => ({
  workflowApi: {
    readFile: (...a: unknown[]) => readFile(...a),
    listInputs: (...a: unknown[]) => listInputs(...a),
    rewriteNote: (...a: unknown[]) => rewriteNote(...a),
    readFileBytes: (...a: unknown[]) => readFileBytes(...a),
  },
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/runs/run-1/notes/ops.md"]}>
          <Routes>
            <Route path="/runs/:runId/notes/:noteRef" element={<WorkflowNotePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

describe("WorkflowNotePage", () => {
  beforeEach(() => {
    readFile.mockResolvedValue({
      path: "inputs/ops.md",
      name: "ops.md",
      size: 40,
      text: "# what ops told me\n\nthe cutover is Friday.\n\n![](pasted.png)",
      truncated: false,
    });
    listInputs.mockResolvedValue({
      items: [{ kind: "note", ref: "ops.md", label: "what ops told me" }],
    });
    rewriteNote.mockResolvedValue({ items: [] });
    readFileBytes.mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    // jsdom has no object URLs.
    globalThis.URL.createObjectURL = vi.fn(() => "blob:ops-image");
    globalThis.URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.clearAllMocks());

  test("renders the note as markdown, under the title the developer gave it", async () => {
    render(wrap());
    expect(await screen.findByRole("heading", { name: "what ops told me", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("the cutover is Friday.")).toBeInTheDocument();
    // Rendered, not shown as source: the note's own `#` became a heading
    // under the page's, rather than a line of literal markdown.
    expect(screen.queryByText(/^# what ops told me/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "what ops told me", level: 2 })).toBeVisible();
  });

  test("an image the note refers to is fetched through the daemon and shown", async () => {
    render(wrap());
    await screen.findByRole("heading", { name: "what ops told me", level: 1 });

    await waitFor(() => expect(readFileBytes).toHaveBeenCalledWith("run-1", "inputs/pasted.png"));
    const image = await screen.findByRole("presentation");
    expect(image).toHaveAttribute("src", "blob:ops-image");
  });

  test("an image whose bytes have not arrived is named, not drawn", async () => {
    // Pointing an <img> at the written `src` would ask this app for a path it
    // does not serve: the SPA answers with its own index.html, the browser
    // cannot decode a document as an image, and every note flashes a broken
    // one on every first paint.
    readFileBytes.mockRejectedValue(new Error("gone"));
    render(wrap());
    await screen.findByRole("heading", { name: "what ops told me", level: 1 });

    await waitFor(() => expect(readFileBytes).toHaveBeenCalled());
    expect(screen.queryByRole("presentation")).not.toBeInTheDocument();
    expect(screen.getByText("pasted.png")).toBeInTheDocument();
  });

  test("editing and saving keeps the ref every task knows the note by", async () => {
    render(wrap());
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    const editor = await screen.findByRole("textbox", { name: "Note" });
    fireEvent.change(editor, { target: { value: "the cutover moved to Monday." } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() =>
      expect(rewriteNote).toHaveBeenCalledWith("run-1", "ops.md", "the cutover moved to Monday."),
    );
  });
});
