// frontend/src/components/knowledge/KnowledgeHandoffs.test.tsx
//
// The Knowledge page's refusals: a curation pass Coffer would not undo (a
// document it wrote was edited since) points at that document's History and
// offers no prompt, while a history that needs git is the neutral row with
// Check again and the install hand-off (carried on the refusal's details as
// `handoff: {prompt}`) on the History tab and on Recent changes. Mocked only
// at the network boundary.
import { afterEach, beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
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
  acceptance("web-ui", "a refused pass undo points at the document's history", async () => {
    api.undoPass.mockRejectedValue(
      new ApiError("KNOWLEDGE_UNDO_CONFLICT", "changed since", {
        version: PASS.version,
        document: GATEWAY.path,
        later_version: "ffff",
      }),
    );
    renderKnowledge(`/knowledge/changes/${PASS.version}`);
    fireEvent.click(await screen.findByRole("button", { name: "Undo this pass" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Undo pass" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    expect(await screen.findByText("Couldn’t undo this pass")).toBeInTheDocument();
    expect(
      screen.getByText(`${GATEWAY.path} changed after it, so nothing was undone.`),
    ).toBeInTheDocument();
    // No hand-off, no prompt: the way out is the document's own History.
    expect(screen.queryByRole("button", { name: /Ask an agent|Copy prompt/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open its History" }));
    expect(screen.getByTestId("where")).toHaveTextContent(
      `/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`,
    );
  });

  acceptance("web-ui", "a history that needs git offers the prompt for installing it", async () => {
    api.getHistory.mockRejectedValue(noGit());
    renderKnowledge(`/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`);
    expect(await screen.findByText("History needs git")).toBeInTheDocument();
    expect(
      screen.getByText("Install git on this Mac to see versions. The document itself is fine."),
    ).toBeInTheDocument();
    // No managed agent here, so the hand-off is the plain Copy prompt.
    fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(GIT_PROMPT);
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Open Activity" })).toBeNull();
  });

  acceptance("web-ui", "recent changes that need git offer the same row", async () => {
    api.listChanges.mockRejectedValue(noGit());
    renderKnowledge("/knowledge");
    expect(await screen.findByText("Recent changes needs git")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(GIT_PROMPT);
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
