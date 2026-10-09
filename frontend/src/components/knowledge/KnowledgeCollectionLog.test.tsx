// frontend/src/components/knowledge/KnowledgeCollectionLog.test.tsx
//
// A collection page's Check section and Change log (spec knowledge "Show a
// collection as one tree of read-only documents in the web UI"): the findings
// grouped by kind, each path opening its file; the changes feed for the
// collection, one row per change — what it did, its writer and time, its
// files, each opening that file with its history drawer — with Show more while
// more are left. Mocked only at the network boundary.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

import { COLLECTION, GATEWAY, NAME, RELEASE, UID, change } from "./knowledgeTestData";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  getTree: vi.fn(),
  getFile: vi.fn(),
  deleteFile: vi.fn(),
  uploadFile: vi.fn(),
  listChanges: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
  getCheck: vi.fn(),
}));
vi.mock("@/lib/api/vault", () => ({
  vaultApi: { history: vi.fn(), diff: vi.fn(), restore: vi.fn() },
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { vaultApi } = await import("@/lib/api/vault");
const ROOT = `/knowledge/${UID}`;

const AGENT_EDIT = change({
  version: "a9e3",
  writer: "agent",
  agent: "claude-code",
  operation: "edit",
  documents: [{ path: GATEWAY.path, status: "modified", added: 4, removed: 1 }],
});

beforeEach(() => {
  answerFromFixtures();
  vi.mocked(vaultApi.history).mockResolvedValue({
    path: `knowledge/${GATEWAY.path}`,
    versions: [],
    next_cursor: null,
  });
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("the Change log", () => {
  acceptance("knowledge", "a collection's change log opens a file at its history", async () => {
    api.listChanges.mockResolvedValue({ changes: [AGENT_EDIT], next_cursor: null });
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    // One row: what it did, its writer and time, the file it touched.
    expect(await within(log).findByText("Edited")).toBeInTheDocument();
    expect(within(log).getByText(/^Claude Code · Today/)).toBeInTheDocument();
    expect(within(log).getByText("+4 −1")).toBeInTheDocument();
    expect(api.listChanges).toHaveBeenCalledWith(expect.objectContaining({ collection: NAME }));

    fireEvent.click(within(log).getByRole("link", { name: "pages/gateway.md" }));
    // The page opens with its history drawer.
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `${ROOT}?file=${encodeURIComponent(GATEWAY.path)}&history=1`,
      ),
    );
    expect(await screen.findByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
    expect(
      await screen.findByRole("complementary", { name: "History of gateway.md" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(vaultApi.history).toHaveBeenCalledWith(`knowledge/${GATEWAY.path}`));
  });

  test("Show more reads the next page while more are left", async () => {
    api.listChanges
      .mockResolvedValueOnce({ changes: [AGENT_EDIT], next_cursor: "p2" })
      .mockResolvedValueOnce({
        changes: [change({ version: "f1le", writer: "daemon", operation: "layout" })],
        next_cursor: null,
      });
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    fireEvent.click(await within(log).findByRole("button", { name: "Show more" }));
    expect(await within(log).findByText("Filed into pages")).toBeInTheDocument();
    expect(within(log).getByText(/^Coffer · /)).toBeInTheDocument();
    expect(api.listChanges).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: "p2" }));
    expect(within(log).queryByRole("button", { name: "Show more" })).toBeNull();
  });

  test("a collection with no changes says so", async () => {
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    expect(await within(log).findByText("No changes yet.")).toBeInTheDocument();
  });
});

describe("the Check section", () => {
  test("lists the findings grouped by kind, each path opening its file", async () => {
    api.getCheck.mockResolvedValue({
      collection: COLLECTION,
      findings: [
        { kind: "waiting_source", path: RELEASE.path, target: null, others: [] },
        { kind: "dead_link", path: GATEWAY.path, target: "gone", others: [] },
        { kind: "orphan_page", path: GATEWAY.path, target: null, others: [] },
      ],
    });
    renderKnowledge(ROOT);
    const check = await screen.findByRole("region", { name: "Check" });
    // Grouped by kind, the links that break a reader first.
    const groups = (await within(check).findAllByRole("heading", { level: 3 })).map(
      (h) => h.firstChild?.textContent,
    );
    expect(groups).toEqual(["Dead links", "Pages nothing links to", "Waiting sources"]);
    expect(within(check).getByText("→ gone")).toBeInTheDocument();

    fireEvent.click(within(check).getByRole("link", { name: "sources/release-notes.md" }));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `${ROOT}?file=${encodeURIComponent(RELEASE.path)}`,
      ),
    );
    expect(await screen.findByRole("heading", { level: 1, name: RELEASE.title })).toBeVisible();
  });

  test("says when nothing was found", async () => {
    renderKnowledge(ROOT);
    const check = await screen.findByRole("region", { name: "Check" });
    expect(await within(check).findByText("Nothing found.")).toBeInTheDocument();
    expect(api.getCheck).toHaveBeenCalledWith(UID);
  });
});
