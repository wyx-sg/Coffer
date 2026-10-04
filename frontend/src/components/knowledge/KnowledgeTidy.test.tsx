// frontend/src/components/knowledge/KnowledgeTidy.test.tsx
//
// Tidy on a collection's page and Tidy all in the Knowledge header (spec
// knowledge "Hand a tidy to the agent"): pressing either opens the draft
// conversation on the default managed agent with the prompt marked to send
// itself; with no managed agent only Copy prompt is offered. Mocked only at the
// network boundary.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import { COLLECTION, UID } from "./knowledgeTestData";
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
  getTidyHandoff: vi.fn(),
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgents = vi.mocked(agentProvidersApi.list);

const ALL_PROMPT = "Tidy every collection, one at a time.";
const writeText = vi.fn().mockResolvedValue(undefined);

const withAgent = (available: boolean) =>
  listAgents.mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available }],
  });

beforeEach(() => {
  answerFromFixtures();
  api.getTidyHandoff.mockResolvedValue({ prompt: ALL_PROMPT });
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("Tidy on a collection's page", () => {
  // Until a hand-off starts the agent in a terminal, Tidy is Copy prompt even with a managed agent.
  test("with a managed agent the page still offers Copy prompt only", async () => {
    withAgent(true);
    renderKnowledge(`/knowledge/${UID}`);
    // The page header's Tidy all is a Copy prompt too; the collection's is the one in its pane.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Copy prompt" })).toHaveLength(2),
    );
    expect(screen.queryByRole("button", { name: "Tidy" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ask an agent" })).toBeNull();
  });

  acceptance("knowledge", "Tidy offers only Copy prompt with no managed agent", async () => {
    withAgent(false);
    renderKnowledge(`/knowledge/${UID}`);
    // The page header's Tidy all is a Copy prompt too; the collection's is the one in its pane.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Copy prompt" })).toHaveLength(2),
    );
    fireEvent.click(screen.getAllByRole("button", { name: "Copy prompt" }).at(-1) as HTMLElement);
    expect(writeText).toHaveBeenCalledWith(COLLECTION.tidy_handoff.prompt);
    expect(screen.queryByRole("button", { name: "Tidy" })).toBeNull();
  });
});

describe("Tidy all in the page header", () => {
  test("Copy prompt fetches the all-collections prompt and copies it", async () => {
    withAgent(true);
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(ALL_PROMPT));
    expect(api.getTidyHandoff).toHaveBeenCalledTimes(1);
  });

  test("with no managed agent Tidy all offers Copy prompt, which fetches the prompt", async () => {
    withAgent(false);
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(ALL_PROMPT));
  });
});
