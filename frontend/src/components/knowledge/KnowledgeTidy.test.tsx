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
  acceptance(
    "knowledge",
    "Tidy sends the prompt to the default managed agent at once",
    async () => {
      withAgent(true);
      renderKnowledge(`/knowledge/${UID}`);
      fireEvent.click(await screen.findByRole("button", { name: "Tidy" }));
      expect(await screen.findByTestId("draft")).toHaveTextContent(
        `claude_code|send|${COLLECTION.tidy_handoff.prompt}`,
      );
    },
  );

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
    expect(screen.queryByTestId("draft")).toBeNull();
  });
});

describe("Tidy all in the page header", () => {
  acceptance("knowledge", "Tidy all sends the prompt like Tidy does", async () => {
    withAgent(true);
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Tidy all" }));
    expect(await screen.findByTestId("draft")).toHaveTextContent(`claude_code|send|${ALL_PROMPT}`);
    expect(api.getTidyHandoff).toHaveBeenCalledTimes(1);
  });

  test("with no managed agent Tidy all offers Copy prompt, which fetches the prompt", async () => {
    withAgent(false);
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(ALL_PROMPT));
    expect(screen.queryByTestId("draft")).toBeNull();
  });
});
