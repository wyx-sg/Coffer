// frontend/src/components/knowledge/KnowledgeFreshness.test.tsx
//
// Keeping a collection current on the Knowledge page (ADR
// knowledge-stays-current-through-flags-coffer-computes): To do lists pages
// that lean on an outdated source and pages due a recheck; an open page says
// it needs rechecking; an open source names what supersedes it; Contents shows
// each source's state and summary, the superseded ones last.
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, vi } from "vitest";

import {
  COLLECTION,
  GATEWAY,
  RELEASE,
  SESSION,
  UID,
  file,
  summary as summaryOf,
} from "@/components/knowledge/knowledgeTestData";
import { acceptance } from "@/test/acceptance";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

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
  getCollectionFiles: vi.fn(),
  undoChange: vi.fn(),
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    listTerminals: vi.fn().mockResolvedValue([]),
    listEditors: vi.fn().mockResolvedValue([]),
    openTerminal: vi.fn(),
  },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const OLD = file(`${COLLECTION.name}/sources/design-v1.md`, {
  kind: "source",
  title: "Design v1",
  page_type: "",
  summary: "The 2024 design.",
  superseded_by: {
    slug: "release-notes",
    path: RELEASE.path,
    title: RELEASE.title,
  },
  cited_by: [{ path: GATEWAY.path, title: GATEWAY.title }],
});
const CURRENT = { ...RELEASE, waiting: false, summary: "What shipped in 3.2." };
const STALE = { ...SESSION, stale: true, verified: "" };

beforeEach(() => {
  answerFromFixtures();
  const fixture = api.getFile.getMockImplementation()!;
  api.getFile.mockImplementation(async (path: string) =>
    path === OLD.path ? OLD : path === STALE.path ? STALE : fixture(path),
  );
});
afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("keeping a collection current", () => {
  acceptance(
    "knowledge",
    "to do lists pages on an outdated source and pages to recheck",
    async () => {
      api.getCheck.mockResolvedValue({
        collection: COLLECTION,
        findings: [
          {
            kind: "superseded_source",
            path: GATEWAY.path,
            target: "design-v1",
            others: [RELEASE.path],
          },
          { kind: "stale_page", path: SESSION.path, target: null, others: [] },
          { kind: "stale_page", path: GATEWAY.path, target: "2026-05-01", others: [] },
        ],
      });
      api.getCollectionFiles.mockResolvedValue({
        files: [GATEWAY, SESSION, CURRENT].map(summaryOf),
      });
      renderKnowledge(`/knowledge/${UID}`);

      const todo = await screen.findByTestId("knowledge-todo");
      expect(await within(todo).findByText("Pages citing an outdated source")).toBeInTheDocument();
      expect(
        within(todo).getByText("cites design-v1, replaced by Release notes"),
      ).toBeInTheDocument();
      expect(within(todo).getByText("Pages to recheck")).toBeInTheDocument();
      expect(within(todo).getByText("never checked")).toBeInTheDocument();
      expect(within(todo).getByText("last checked 2026-05-01")).toBeInTheDocument();
    },
  );

  acceptance("knowledge", "a page due a recheck says so", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(STALE.path)}`);
    const line = await screen.findByTestId("file-line");
    expect(within(line).getByText("Needs rechecking")).toBeInTheDocument();
    expect(within(line).getByText("never checked")).toBeInTheDocument();
  });

  acceptance("knowledge", "a superseded source names its replacement", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(OLD.path)}`);
    const line = await screen.findByTestId("file-line");
    expect(line).toHaveTextContent("Superseded by");
    expect(within(line).getByRole("link", { name: "Release notes" })).toBeInTheDocument();
  });

  acceptance(
    "knowledge",
    "contents shows each source's state and summary, superseded last",
    async () => {
      api.getCollectionFiles.mockResolvedValue({
        files: [OLD, CURRENT, GATEWAY].map(summaryOf),
      });
      renderKnowledge(`/knowledge/${UID}`);
      const card = await screen.findByTestId("knowledge-contents-sources");
      const rows = within(card).getAllByRole("listitem");
      expect(rows[0]).toHaveTextContent("Release notes");
      expect(rows[0]).toHaveTextContent("used by 0 pages");
      expect(rows[0]).toHaveTextContent("What shipped in 3.2.");
      expect(rows[1]).toHaveTextContent("Design v1");
      expect(rows[1]).toHaveTextContent("superseded");
      expect(rows[1]).toHaveTextContent("The 2024 design.");
    },
  );
});
