// frontend/src/components/knowledge/KnowledgeShell.test.tsx
//
// The Knowledge page's shell (boards 5.1.01, 5.1.03, 5.1.09, 5.1.11, 5.1.12,
// 5.1.13, 5.1.26–28; Foundations 0.6.04): the header (title, Experimental tag,
// one subtitle, Tidy all and the one primary Upload), the first-run empty
// state, the tree (a Collections strip with New collection, the unsaved dot)
// and the Upload dialog's Cancel. Mocked only at the network boundary, like the page tests.
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { COLLECTION, GATEWAY, OTHER, UID } from "@/components/knowledge/knowledgeTestData";
import { setDirtyDocument, setEditingDocument } from "@/lib/knowledge/dirtyDocument";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

import { acceptance } from "@/test/acceptance";

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
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: {
    list: vi.fn().mockResolvedValue({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
    }),
  },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const SUBTITLE = "Documents you and your agents write together. Every agent can read them.";

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  act(() => {
    setDirtyDocument(null);
    setEditingDocument(null);
  });
  vi.clearAllMocks();
});

function tree() {
  return screen.getByRole("navigation", { name: "Collections and documents" });
}

describe("the header", () => {
  acceptance("knowledge", "the page's one primary action is Upload", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    const tidyAll = await within(screen.getByRole("banner")).findByRole("button", {
      name: "Tidy all",
    });
    expect(within(screen.getByRole("banner")).getByRole("heading")).toHaveTextContent("Knowledge");
    expect(screen.getByText("Experimental")).toBeInTheDocument();
    expect(screen.getByText(SUBTITLE)).toBeInTheDocument();
    expect(tidyAll.className).not.toMatch(/bg-accent/);
    // No curation control any more: no Automatic button, no engine link.
    expect(screen.queryByTestId("knowledge-automatic")).toBeNull();
    const upload = screen.getByRole("button", { name: "Upload" });
    expect(upload.className).toMatch(/bg-accent/);
    // Upload sits to the right of Tidy all.
    expect(tidyAll.compareDocumentPosition(upload) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // "Add a document" no longer exists.
    expect(screen.queryByRole("button", { name: "Add a document" })).toBeNull();
    // 16 top / 32 sides / 12 bottom, no divider.
    const header = screen.getByRole("banner");
    expect(header.parentElement?.className).toMatch(/px-8/);
    expect(header.parentElement?.className).not.toMatch(/border-b/);
  });

  test("Upload drops to secondary while a document is being edited", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    await screen.findByRole("button", { name: "Tidy all" });
    act(() => setEditingDocument(GATEWAY.path));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Upload" }).className).not.toMatch(/bg-accent/),
    );
  });
});

describe("first run", () => {
  test("no collections: the standard empty state with New collection, no Upload or Tidy all", async () => {
    api.listCollections.mockResolvedValue({ collections: [] });
    renderKnowledge("/knowledge");
    expect(await screen.findByText("No collections yet")).toBeInTheDocument();
    expect(screen.getByText(/A collection is a folder of Markdown documents/)).toBeInTheDocument();
    expect(screen.getByText(SUBTITLE)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Tidy all" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "New collection" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Every agent sees it through the coffer-guide skill."),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" }).className).toMatch(
      /bg-transparent/,
    );
  });
});

describe("the tree", () => {
  test("no node shows a count and no Inbox node is listed; Collections strip holds New collection", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    const nav = tree();
    await within(nav).findByRole("button", { name: "gateway.md" });
    expect(within(nav).queryByRole("button", { name: /^Inbox/ })).toBeNull();
    // The collection rows and Recent changes carry no number.
    const row = within(nav).getByRole("button", { name: new RegExp(`^${COLLECTION.name}$`) });
    expect(row).not.toHaveTextContent(/\d/);
    expect(within(nav).getByRole("link", { name: "Recent changes" })).not.toHaveTextContent(/\d/);
    // A collection with no documents shows no "0".
    fireEvent.click(within(nav).getByRole("button", { name: `Expand ${OTHER.name}` }));
    expect(nav.textContent).not.toMatch(/(^|\s)0(\s|$)/);
    // New collection is the strip's icon button; there is no bottom "+ New collection".
    expect(within(nav).getAllByRole("button", { name: "New collection" })).toHaveLength(1);
    fireEvent.click(within(nav).getByRole("button", { name: "New collection" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("New collection");
  });

  test("the file with unsaved edits shows an accent dot", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    const nav = tree();
    await within(nav).findByRole("button", { name: "gateway.md" });
    expect(within(nav).queryByRole("img", { name: "Unsaved changes" })).toBeNull();
    act(() => setDirtyDocument(GATEWAY.path));
    const dot = await within(nav).findByRole("img", { name: "Unsaved changes" });
    expect(within(nav).getByRole("button", { name: /^gateway\.md/ })).toContainElement(dot);
  });
});

describe("the Upload dialog", () => {
  test("Cancel stays live while converting and aborts the upload", async () => {
    let signal: AbortSignal | undefined;
    api.uploadFile.mockImplementation(
      (params: { signal?: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          signal = params.signal;
          params.signal?.addEventListener("abort", () =>
            reject(new DOMException("x", "AbortError")),
          );
        }),
    );
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Upload" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(
        "Coffer converts it to Markdown and adds it to the collection as a document. The original file isn’t kept.",
      ),
    ).toBeInTheDocument();
    const input = within(dialog).getByLabelText("Drop a file here, or choose one");
    fireEvent.change(input, {
      target: { files: [new File(["hello"], "notes.md", { type: "text/markdown" })] },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(api.uploadFile).toHaveBeenCalled());
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    expect(cancel).toBeEnabled();
    fireEvent.click(cancel);
    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
