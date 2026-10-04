// frontend/src/components/knowledge/KnowledgeDocument.test.tsx
//
// One open knowledge document (boards 5.1.01–5.1.04, 5.1.29): the reader with
// its single properties line and no side rail, the pane bar (full path, tabs
// without counts, Preview / Source, Edit, ⋯), delete at once with an Undo
// toast, the editor's Discard / Save and unsaved state, the leave-without-
// saving guard, and a refused save → banner → in-page Compare. Mocked only at
// the network boundary, like the Knowledge page tests.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";

import { UnsavedGuardProvider } from "@/components/shell/UnsavedGuard";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { KnowledgePage } from "@/pages/KnowledgePage";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

import { GATEWAY, PASS, UID } from "./knowledgeTestData";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  getTree: vi.fn(),
  getFile: vi.fn(),
  saveFile: vi.fn(),
  deleteFile: vi.fn(),
  uploadFile: vi.fn(),
  listChanges: vi.fn(),
  getHistory: vi.fn(),
  getVersionDiff: vi.fn(),
  getVersionBody: vi.fn(),
  restoreVersion: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const OPEN = `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`;
const ROOT = new RegExp(`/knowledge/${UID}$`);

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  vi.clearAllMocks();
});

const editor = () => screen.getByRole("textbox", { name: `Edit ${GATEWAY.path}` });

async function startEditing(text?: string) {
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  if (text !== undefined) fireEvent.change(editor(), { target: { value: text } });
}

/** Edit, change the text, and have the save refused as stale because an agent changed the file. */
async function refusedSave() {
  api.saveFile.mockRejectedValue(
    new ApiError("KNOWLEDGE_FILE_CONFLICT", "changed on disk", {
      saved: false,
      current_body: "# Account Gateway\n\nAn agent added a line.",
      current_fingerprint: "fp-new",
    }),
  );
  api.getHistory.mockResolvedValue({
    path: GATEWAY.path,
    versions: [
      {
        change: {
          ...PASS,
          writer: "agent" as const,
          operation: "save",
          time: "2026-10-03T14:05:00",
        },
        removed: false,
      },
    ],
  });
  renderKnowledge(OPEN);
  await startEditing("My version.");
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  return await screen.findByRole("alert");
}

describe("the reader", () => {
  test("has no side rail and no curated card, only one properties line under the title", async () => {
    api.getHistory.mockResolvedValue({
      path: GATEWAY.path,
      versions: [{ change: PASS, removed: false }],
    });
    renderKnowledge(OPEN);
    expect(await screen.findByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(screen.queryByText("On this page")).toBeNull();
    expect(screen.queryByText("Properties")).toBeNull();
    expect(screen.queryByText(/See what this pass changed/)).toBeNull();
    // The oldest version is an earlier curation pass: it keeps its label, and no pass is linked.
    const line = await screen.findByText(/Created Sep 12 by Curation/);
    expect(line).not.toHaveTextContent("Curated");
    expect(screen.queryByRole("link", { name: "See the pass" })).toBeNull();
  });

  test("leaves a part out when it has no data", async () => {
    renderKnowledge(OPEN);
    const created = await screen.findByText(/^Created Sep 12 by/);
    expect(created).not.toHaveTextContent("Curated");
  });

  test("a file written on disk dates itself by its first version and names no writer", async () => {
    api.getFile.mockResolvedValue({ ...GATEWAY, created_at: "", actor: "agent" });
    api.getHistory.mockResolvedValue({
      path: GATEWAY.path,
      versions: [
        {
          change: { ...PASS, operation: "edit", writer: "disk", time: "2026-10-03T12:06:37Z" },
          removed: false,
        },
      ],
    });
    renderKnowledge(OPEN);
    expect(await screen.findByText(/^Created Oct 3$/)).toBeVisible();
    expect(screen.queryByText(/Invalid Date/)).toBeNull();
  });

  test("the bar names the full path, has tabs without counts, and Preview / Source", async () => {
    api.getHistory.mockResolvedValue({
      path: GATEWAY.path,
      versions: [{ change: PASS, removed: false }],
    });
    renderKnowledge(OPEN);
    const where = await screen.findByRole("navigation", { name: "Where this document is" });
    expect(where).toHaveTextContent("shopee");
    expect(where).toHaveTextContent("gateway.md");
    expect(screen.getByRole("link", { name: "History" })).toHaveTextContent(/^History$/);

    const preview = await screen.findByRole("button", { name: "Preview" });
    expect(preview).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    expect(screen.getByRole("button", { name: "Source" })).toHaveAttribute("aria-pressed", "true");
    // Source is the raw text: the heading is shown as written, not rendered.
    expect(screen.queryByRole("heading", { name: GATEWAY.title })).toBeNull();
  });

  test("the ⋯ menu holds the file actions and Delete document… after a separator", async () => {
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Open in editor", "Reveal in Finder", "Delete document…"]);
  });
});

describe("delete a document", () => {
  async function deleteIt() {
    api.deleteFile.mockResolvedValue(undefined);
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete document…" }));
  }

  test("runs at once, with no confirmation, and goes to the collection", async () => {
    await deleteIt();
    await waitFor(() => expect(api.deleteFile).toHaveBeenCalledWith(GATEWAY.path));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText("Deleted gateway.md")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(ROOT));
  });

  test("its toast's Undo restores the delete from Recent changes", async () => {
    const deletion = {
      ...PASS,
      version: "d3l3t3",
      writer: "user" as const,
      operation: "delete",
      documents: [{ path: GATEWAY.path, status: "removed" as const, added: 0, removed: 3 }],
    };
    api.listChanges.mockResolvedValue({ changes: [deletion], next_cursor: null });
    api.restoreDeleted.mockResolvedValue(deletion);
    await deleteIt();
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(api.restoreDeleted).toHaveBeenCalledWith("d3l3t3"));
  });

  test("a refused delete is an error toast and the pane stays on the document", async () => {
    api.deleteFile.mockRejectedValue(new ApiError("INTERNAL", "nope"));
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete document…" }));
    expect(await screen.findByText("Couldn’t delete gateway.md")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("file=");
  });
});

describe("the editor", () => {
  test("Discard and Save sit in the bar, unsaved is a dot beside them, no bottom status bar", async () => {
    renderKnowledge(OPEN);
    await startEditing();
    expect(screen.getByRole("button", { name: "Discard" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.queryByText("Unsaved changes")).toBeNull();
    fireEvent.change(editor(), { target: { value: "Changed." } });
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    // The old footer (Markdown · ⌘S save · esc cancel) is gone.
    expect(screen.queryByText("esc")).toBeNull();
    expect(screen.queryByText("Markdown")).toBeNull();
    // Front matter is a read-only grid.
    expect(screen.getByText("title")).toBeInTheDocument();
    expect(screen.queryByText("Kept by curation")).toBeNull();
    expect(screen.queryByText(/Read-only here/)).toBeNull();
  });

  test("⌘S saves and Esc discards, asking first when the text changed", async () => {
    api.saveFile.mockResolvedValue({ ...GATEWAY, body: "Changed.", fingerprint: "fp-2" });
    renderKnowledge(OPEN);
    await startEditing("Changed.");
    fireEvent.keyDown(editor(), { key: "Escape" });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(editor()).toHaveValue("Changed.");
    fireEvent.keyDown(editor(), { key: "s", metaKey: true });
    await waitFor(() =>
      expect(api.saveFile).toHaveBeenCalledWith({
        path: GATEWAY.path,
        body: "Changed.",
        expected_fingerprint: GATEWAY.fingerprint,
      }),
    );
  });

  test("leaving a dirty document asks first; a clean one leaves quietly", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const app = (
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <TooltipProvider>
            <UnsavedGuardProvider>
              <KnowledgePage />
              <Link to="/activity">elsewhere</Link>
            </UnsavedGuardProvider>
          </TooltipProvider>
        </ToastProvider>
      </QueryClientProvider>
    );
    const router = createMemoryRouter(
      [
        { path: "/knowledge/:uid", element: app },
        { path: "/knowledge/:uid/:tab", element: app },
        { path: "*", element: <p>elsewhere open</p> },
      ],
      { initialEntries: [OPEN] },
    );
    render(<RouterProvider router={router} />);
    await startEditing("Changed.");
    fireEvent.click(screen.getByRole("link", { name: "elsewhere" }));
    const dialog = await screen.findByRole("dialog", { name: "Leave without saving?" });
    expect(dialog).toHaveTextContent("You edited gateway.md in shopee");
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(router.state.location.pathname).toBe(`/knowledge/${UID}`);
    expect(editor()).toHaveValue("Changed.");
    // Switching to the History tab is leaving too.
    fireEvent.click(screen.getByRole("link", { name: "History" }));
    expect(await screen.findByRole("dialog", { name: "Leave without saving?" })).toBeVisible();
  });
});

describe("a refused save", () => {
  test("shows a banner naming who changed it, Compare / Copy my text / Reload…, and 'Not saved'", async () => {
    const alert = await refusedSave();
    expect(alert).toHaveTextContent("This document changed on disk while you were editing");
    await waitFor(() => expect(alert).toHaveTextContent(/Codex changed gateway\.md at 14:05\./));
    expect(alert).toHaveTextContent("Your text isn’t saved yet.");
    expect(within(alert).getByRole("button", { name: "Compare" })).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Copy my text" })).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Reload…" })).toBeInTheDocument();
    expect(screen.getByText("Not saved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  test("Reload… asks before it drops the text", async () => {
    const alert = await refusedSave();
    fireEvent.click(within(alert).getByRole("button", { name: "Reload…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
  });

  test("Compare is an in-page view whose diff follows the choice", async () => {
    const alert = await refusedSave();
    fireEvent.click(within(alert).getByRole("button", { name: "Compare" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Which version to keep?")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Keep my edit/ })).toBeChecked();
    expect(screen.getByText(/Codex · /)).toBeInTheDocument();
    expect(screen.getByText(/keep your edit\.$/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: /Take the version on disk/ }));
    expect(screen.getByText(/take the version on disk\.$/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use the disk version" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save my edit" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Back to editing" }));
    expect(editor()).toHaveValue("My version.");
  });

  test("Save my edit saves over the disk's fingerprint and leaves the editor", async () => {
    const alert = await refusedSave();
    api.saveFile.mockReset();
    api.saveFile.mockResolvedValue({ ...GATEWAY, body: "My version.", fingerprint: "fp-3" });
    fireEvent.click(within(alert).getByRole("button", { name: "Compare" }));
    fireEvent.click(screen.getByRole("button", { name: "Save my edit" }));
    await waitFor(() =>
      expect(api.saveFile).toHaveBeenCalledWith({
        path: GATEWAY.path,
        body: "My version.",
        expected_fingerprint: "fp-new",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
  });

  test("Use the disk version takes the disk's text", async () => {
    const alert = await refusedSave();
    fireEvent.click(within(alert).getByRole("button", { name: "Compare" }));
    fireEvent.click(screen.getByRole("radio", { name: /Take the version on disk/ }));
    fireEvent.click(screen.getByRole("button", { name: "Use the disk version" }));
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(api.saveFile).toHaveBeenCalledTimes(1);
  });
});
