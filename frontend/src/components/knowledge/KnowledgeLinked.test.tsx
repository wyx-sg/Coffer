// frontend/src/components/knowledge/KnowledgeLinked.test.tsx
//
// A linked folder on the Knowledge page (spec knowledge "Link a folder the
// person keeps themselves"): the Add menu's dialog says the files stay where
// they are, the folder's page shows what it is and offers nothing to manage,
// its files have no History or Delete, and an upload never lands in it.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, vi } from "vitest";

import { COLLECTION, OTHER, file } from "@/components/knowledge/knowledgeTestData";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";
import { acceptance } from "@/test/acceptance";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  linkFolder: vi.fn(),
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
    pickFolder: vi.fn(),
    browse: vi.fn(),
  },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const WORK: CollectionOut = {
  uid: "kn-work",
  name: "Work",
  description: "My work notes.",
  page_count: 0,
  source_count: 0,
  waiting_source_count: 0,
  finding_count: 0,
  folder_path: "/Users/u/Obsidian/Work",
  updated_at: null,
  tidy_handoff: { prompt: "" },
  tidy_running: false,
  linked: true,
  note_count: 12,
  rules_file: "AGENTS.md",
};
const NOTE = file("Work/Projects/Gateway.md", {
  title: "Payment gateway",
  body: "Timeouts are 3s.",
  file_path: "/Users/u/Obsidian/Work/Projects/Gateway.md",
  folder_path: "/Users/u/Obsidian/Work/Projects",
});

beforeEach(() => {
  answerFromFixtures();
  api.listCollections.mockResolvedValue({ collections: [COLLECTION, OTHER, WORK] });
  const fixtureFile = api.getFile.getMockImplementation();
  api.getFile.mockImplementation(async (path: string) =>
    path === NOTE.path ? NOTE : fixtureFile!(path),
  );
});
afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("linking a folder", () => {
  acceptance("knowledge", "the link dialog says the files stay where they are", async () => {
    api.linkFolder.mockResolvedValue(WORK);
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Link an external folder/ }));

    const dialog = await screen.findByRole("dialog", { name: "Link an external folder" });
    const note = within(dialog).getByRole("note");
    expect(note).toHaveTextContent("The files stay where they are. Nothing is copied into Coffer.");
    expect(note).toHaveTextContent("Coffer doesn't sync it, tidy it, keep its history");
    fireEvent.change(within(dialog).getByLabelText("Folder"), {
      target: { value: "/Users/u/Obsidian/Work" },
    });
    // The name follows the folder until the person types one.
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Work");
    fireEvent.click(within(dialog).getByRole("button", { name: "Link folder" }));

    await waitFor(() =>
      expect(api.linkFolder).toHaveBeenCalledWith({
        folder: "/Users/u/Obsidian/Work",
        name: "Work",
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent("/knowledge/kn-work"),
    );
  });
});

describe("a linked folder's page", () => {
  acceptance("knowledge", "a linked folder's page shows who manages it", async () => {
    renderKnowledge("/knowledge/kn-work");
    const heading = await screen.findByRole("heading", { name: /Work/ });
    expect(within(heading).getByText("External")).toBeInTheDocument();
    const facts = screen.getByLabelText("About this folder");
    expect(facts).toHaveTextContent("/Users/u/Obsidian/Work");
    expect(facts).toHaveTextContent("12 Markdown notes");
    expect(facts).toHaveTextContent("AGENTS.md");
    expect(facts).toHaveTextContent("Its own tools. Coffer only shares it with agents");
    // Nothing to manage: no Tidy, To do, Contents or Change log.
    expect(screen.queryByRole("button", { name: /Tidy/ })).toBeNull();
    expect(screen.queryByRole("region", { name: "To do" })).toBeNull();
    expect(screen.queryByTestId("knowledge-summary")).toBeNull();
    expect(api.getCheck).not.toHaveBeenCalled();
    expect(api.listChanges).not.toHaveBeenCalledWith(
      expect.objectContaining({ collection: "Work" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "More actions for Work" }));
    const items = (await screen.findAllByRole("menuitem")).map((i) => i.textContent);
    expect(items).toContain("Disconnect…");
    expect(items).not.toContain("Delete collection…");
  });

  acceptance("knowledge", "a linked folder's note has no history or delete", async () => {
    renderKnowledge(`/knowledge/kn-work?file=${encodeURIComponent(NOTE.path)}`);
    await screen.findByText("Timeouts are 3s.");
    expect(screen.queryByRole("button", { name: "History" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: `More actions for ${NOTE.path}` }));
    const items = (await screen.findAllByRole("menuitem")).map((i) => i.textContent);
    expect(items).not.toContain("Delete…");
  });

  acceptance("knowledge", "an upload never lands in a linked folder", async () => {
    renderKnowledge("/knowledge/kn-work");
    fireEvent.click(await screen.findByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Upload documents/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("combobox"));
    const options = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(options.join(" ")).not.toContain("Work");
  });
});
