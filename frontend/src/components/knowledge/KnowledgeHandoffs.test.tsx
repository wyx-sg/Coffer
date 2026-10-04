// frontend/src/components/knowledge/KnowledgeHandoffs.test.tsx
//
// The Knowledge page's refusals: a history that needs git is the neutral row
// with Check again and the install hand-off (carried on the refusal's details
// as `handoff: {prompt}`) on the History tab and on Recent changes. Mocked only
// at the network boundary.
import { afterEach, beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import { GATEWAY, UID } from "./knowledgeTestData";
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
const noGit = () =>
  new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "no git", {
    reason: "git_missing",
    handoff: { prompt: GIT_PROMPT },
  });

/** With no managed agent the page header's Tidy all is a Copy prompt too; the row's is the last. */
const copyPromptInPane = () =>
  screen.getAllByRole("button", { name: "Copy prompt" }).at(-1) as HTMLElement;

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  answerFromFixtures();
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("knowledge hand-offs", () => {
  acceptance("web-ui", "a history that needs git offers the prompt for installing it", async () => {
    api.getHistory.mockRejectedValue(noGit());
    renderKnowledge(`/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`);
    expect(await screen.findByText("History needs git")).toBeInTheDocument();
    expect(
      screen.getByText("Install git on this Mac to see versions. The document itself is fine."),
    ).toBeInTheDocument();
    // No managed agent here, so the hand-off is the plain Copy prompt.
    fireEvent.click(copyPromptInPane());
    expect(writeText).toHaveBeenCalledWith(GIT_PROMPT);
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Open Activity" })).toBeNull();
  });

  acceptance("web-ui", "recent changes that need git offer the same row", async () => {
    api.listChanges.mockRejectedValue(noGit());
    renderKnowledge("/knowledge");
    expect(await screen.findByText("Recent changes needs git")).toBeInTheDocument();
    fireEvent.click(copyPromptInPane());
    expect(writeText).toHaveBeenCalledWith(GIT_PROMPT);
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
