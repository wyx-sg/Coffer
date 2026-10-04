// frontend/src/components/knowledge/KnowledgeRecentChanges.test.tsx
//
// Recent changes as boards 5.1.21–5.1.24 draw them, mocked only at the network
// boundary: Collection and Author pills kept in the address with Clear
// filters, a change an earlier curation pass made keeping its curation label,
// Restore as a small button, and the two ways the region fails.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import { EDIT, NAME, OTHER, PASS } from "./knowledgeTestData";
import { ApiError } from "@/lib/api/errors";

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
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const GIT_PROMPT = "Please install git on this machine.";
const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  answerFromFixtures();
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => {
  vi.clearAllMocks();
});

const where = () => screen.getByTestId("where");

describe("filters", () => {
  acceptance("web-ui", "the filter pills narrow the timeline and live in the URL", async () => {
    renderKnowledge("/knowledge");
    await screen.findByRole("link", { name: "gateway.md" });
    // The old segmented control and select are gone.
    expect(screen.queryByRole("button", { name: "Everyone" })).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();

    // Authors come from the changes: you, and Curation for the pass.
    fireEvent.click(screen.getByRole("button", { name: /^Author/ }));
    const list = await screen.findByRole("listbox", { name: "Author" });
    expect(
      within(list)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["You", "Curation"]);
    fireEvent.click(within(list).getByRole("option", { name: "You" }));
    expect(where()).toHaveTextContent("/knowledge?author=user");
    expect(screen.queryByRole("link", { name: "gateway.md" })).toBeNull();
    expect(screen.getByRole("link", { name: "on-call.md" })).toBeInTheDocument();

    // Collection asks the daemon for that collection's changes only.
    api.listChanges.mockImplementation(async ({ collection }) => ({
      changes: collection === OTHER.name ? [EDIT] : [PASS, EDIT],
      next_cursor: null,
    }));
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: /^Collection/ }));
    fireEvent.click(await screen.findByRole("option", { name: OTHER.name }));
    await waitFor(() =>
      expect(api.listChanges).toHaveBeenLastCalledWith(
        expect.objectContaining({ collection: OTHER.name }),
      ),
    );
    expect(where()).toHaveTextContent("collection=runbooks");

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(where()).toHaveTextContent(/^\/knowledge$/);
    await waitFor(() => expect(screen.getByRole("link", { name: "gateway.md" })).toBeVisible());
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();
  });

  test("a filter in the address is applied on arrival", async () => {
    renderKnowledge("/knowledge?author=curation");
    expect(await screen.findByRole("link", { name: "gateway.md" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "on-call.md" })).toBeNull();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  test("the heading is plain, with no counts anywhere", async () => {
    renderKnowledge("/knowledge");
    const heading = await screen.findByRole("heading", { name: "Recent changes" });
    expect(heading.className).not.toMatch(/\[16px\]/);
    expect(screen.getByText("Last 7 days")).toBeInTheDocument();
    expect(screen.queryByText(/\d+ items?\b/)).toBeNull();
  });
});

describe("a change an earlier curation pass made", () => {
  acceptance("web-ui", "recent changes shows a cross-collection timeline", async () => {
    renderKnowledge("/knowledge");
    // Both changes, each linking the document it wrote, and nothing waiting or to inspect.
    expect(await screen.findByRole("link", { name: "gateway.md" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "on-call.md" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Waiting to be curated" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Curate now" })).toBeNull();
    expect(screen.queryByRole("link", { name: "See the pass" })).toBeNull();
  });

  test("keeps its curation label and its summary", async () => {
    renderKnowledge("/knowledge");
    await screen.findByRole("link", { name: "gateway.md" });
    expect(screen.getByText("Curation")).toBeInTheDocument();
    expect(screen.getByText(PASS.summary)).toBeInTheDocument();
  });
});

describe("the rows", () => {
  test("a document link is accent and Restore is a small secondary button", async () => {
    const DELETE = {
      ...EDIT,
      version: "de1e7e00",
      operation: "delete",
      documents: [{ path: `${NAME}/gone.md`, status: "removed" as const, added: 0, removed: 3 }],
    };
    api.listChanges.mockResolvedValue({
      changes: [PASS, DELETE],
      next_cursor: null,
    });
    renderKnowledge("/knowledge");
    const link = await screen.findByRole("link", { name: "gateway.md" });
    expect(link.className).toMatch(/text-accent-text/);
    expect(link.className).not.toMatch(/underline/);
    const restore = screen.getByRole("button", { name: "Restore" });
    expect(restore.className).toMatch(/h-control-sm/);
    expect(restore.className).toMatch(/border-border/);
  });
});

describe("when the region cannot load", () => {
  acceptance("web-ui", "recent changes that need git offer the same row", async () => {
    api.listChanges.mockRejectedValue(
      new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "no git", {
        reason: "git_missing",
        handoff: { prompt: GIT_PROMPT },
      }),
    );
    renderKnowledge("/knowledge");
    expect(await screen.findByText("Recent changes needs git")).toBeInTheDocument();
    expect(
      screen.getByText("Install git on this Mac to see what changed. Your documents are fine."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    // No managed agent here, so the hand-off is the plain Copy prompt.
    fireEvent.click(screen.getAllByRole("button", { name: "Copy prompt" }).at(-1) as HTMLElement);
    expect(writeText).toHaveBeenCalledWith(GIT_PROMPT);
    const before = api.listChanges.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.listChanges.mock.calls.length).toBe(before + 1));
  });

  test("any other failure: a danger row with Retry and Open Activity", async () => {
    api.listChanges.mockRejectedValue(new ApiError("INTERNAL", "boom"));
    renderKnowledge("/knowledge");
    expect(await screen.findByText("Couldn't read recent changes")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    const before = api.listChanges.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.listChanges.mock.calls.length).toBe(before + 1));
    fireEvent.click(screen.getByRole("link", { name: "Open Activity" }));
    expect(where()).toHaveTextContent("/activity");
  });
});
