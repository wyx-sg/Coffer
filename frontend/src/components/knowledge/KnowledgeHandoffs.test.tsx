// frontend/src/components/knowledge/KnowledgeHandoffs.test.tsx
//
// The Knowledge page's two hand-offs, each carried on a refusal's details as
// `handoff: {prompt}`: a curation pass Coffer would not undo (a document it
// wrote was edited since) offers the prompt for undoing it by hand beside the
// refusal, and a history that needs git offers the prompt for installing it
// on the History tab and on Recent changes. Mocked only at the network boundary.
import { afterEach, beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "./knowledgeTestHarness";
import { GATEWAY, PASS, UID } from "./knowledgeTestData";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  getTree: vi.fn(),
  getFile: vi.fn(),
  saveFile: vi.fn(),
  deleteFile: vi.fn(),
  curateCollection: vi.fn(),
  uploadFile: vi.fn(),
  submitMaterial: vi.fn(),
  listChanges: vi.fn(),
  getChange: vi.fn(),
  undoPass: vi.fn(),
  getHistory: vi.fn(),
  getVersionDiff: vi.fn(),
  getVersionBody: vi.fn(),
  restoreVersion: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
}));
vi.mock("@/lib/api/internalEngine", () => ({ internalEngineApi: { get: vi.fn() } }));
vi.mock("@/lib/api/upkeep", () => ({ listUpkeepRuns: vi.fn() }));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const UNDO_PROMPT = "Please undo the knowledge curation pass by hand.";
const GIT_PROMPT = "Please install git on this machine.";
const noGit = () =>
  new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "no git", {
    reason: "git_missing",
    handoff: { prompt: GIT_PROMPT },
  });

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  answerFromFixtures();
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("knowledge hand-offs", () => {
  acceptance("web-ui", "a refused pass undo offers the prompt for undoing it by hand", async () => {
    api.undoPass.mockRejectedValue(
      new ApiError("KNOWLEDGE_UNDO_CONFLICT", "changed since", {
        version: PASS.version,
        document: GATEWAY.path,
        later_version: "ffff",
        handoff: { prompt: UNDO_PROMPT },
      }),
    );
    renderKnowledge(`/knowledge/changes/${PASS.version}`);
    fireEvent.click(await screen.findByRole("button", { name: "Undo this pass" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Undo pass" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const note = (await screen.findByText("Couldn't undo this pass")).closest("[role=status]");
    expect(note).not.toBeNull();
    // The per-document History restore is still named; the hand-off sits beside it.
    expect(within(note as HTMLElement).getByText(/Restore a single document/)).toBeInTheDocument();
    fireEvent.click(within(note as HTMLElement).getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(UNDO_PROMPT);
  });

  acceptance("web-ui", "a history that needs git offers the prompt for installing it", async () => {
    api.getHistory.mockRejectedValue(noGit());
    renderKnowledge(`/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`);
    expect(await screen.findByText("Couldn't read this document's history")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(GIT_PROMPT);
    // The error's own words name no install command.
    expect(screen.getByText(/git is not installed on this machine/)).toBeInTheDocument();
  });

  acceptance(
    "web-ui",
    "recent changes that need git offer the prompt for installing it",
    async () => {
      api.listChanges.mockRejectedValue(noGit());
      renderKnowledge("/knowledge");
      fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
      expect(writeText).toHaveBeenCalledWith(GIT_PROMPT);
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    },
  );
});
