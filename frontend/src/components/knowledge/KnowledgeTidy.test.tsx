// frontend/src/components/knowledge/KnowledgeTidy.test.tsx
//
// Tidy and Check with agent on a collection's page and Tidy all in the
// Knowledge header (spec knowledge "Hand a tidy to the agent", "Hand a check to
// the agent"): pressing any asks the daemon to start
// the hand-off agent in the preferred terminal with the prompt sent; with no managed
// agent only Copy prompt is offered. Mocked only at the network boundary.
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
  deleteFile: vi.fn(),
  uploadFile: vi.fn(),
  listChanges: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
  getCheck: vi.fn(),
  getTidyHandoff: vi.fn(),
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/api/fs", () => ({ fsApi: { listTerminals: vi.fn(), openTerminal: vi.fn() } }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const { fsApi } = await import("@/lib/api/fs");
const listAgents = vi.mocked(agentProvidersApi.list);
const openTerminal = vi.mocked(fsApi.openTerminal);

const ALL_PROMPT = "Tidy every collection, one at a time.";
const writeText = vi.fn().mockResolvedValue(undefined);

const withAgent = (available: boolean) =>
  listAgents.mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available }],
  });

beforeEach(() => {
  answerFromFixtures();
  api.getTidyHandoff.mockResolvedValue({ prompt: ALL_PROMPT });
  vi.mocked(fsApi.listTerminals).mockResolvedValue([]);
  openTerminal.mockResolvedValue(undefined);
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
      // The hand-off agent starts in the preferred terminal with the collection's prompt, once.
      await waitFor(() =>
        expect(openTerminal).toHaveBeenCalledWith({
          agent: "claude_code",
          prompt: COLLECTION.tidy_handoff.prompt,
          terminal: null,
        }),
      );
      expect(openTerminal).toHaveBeenCalledTimes(1);
      // The page stays where it is.
      expect(screen.getByRole("button", { name: "Tidy" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Hand off to/ })).toBeNull();
    },
  );

  acceptance("knowledge", "Tidy offers only Copy prompt with no managed agent", async () => {
    withAgent(false);
    renderKnowledge(`/knowledge/${UID}`);
    // The page header's Tidy all is a Copy prompt too, and so is the pane's
    // Check with agent; the collection's Tidy is the one before it in its pane.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Copy prompt" })).toHaveLength(3),
    );
    fireEvent.click(screen.getAllByRole("button", { name: "Copy prompt" })[1] as HTMLElement);
    expect(writeText).toHaveBeenCalledWith(COLLECTION.tidy_handoff.prompt);
    expect(screen.queryByRole("button", { name: "Tidy" })).toBeNull();
    expect(openTerminal).not.toHaveBeenCalled();
  });
});

describe("Check with agent on a collection's page", () => {
  test("sends the collection's check prompt to the default managed agent at once", async () => {
    withAgent(true);
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Check with agent" }));
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith({
        agent: "claude_code",
        prompt: COLLECTION.check_handoff.prompt,
        terminal: null,
      }),
    );
    expect(openTerminal).toHaveBeenCalledTimes(1);
    // It sits beside Tidy, after it.
    const tidy = screen.getByRole("button", { name: "Tidy" });
    const check = screen.getByRole("button", { name: "Check with agent" });
    expect(tidy.compareDocumentPosition(check) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("Tidy all in the page header", () => {
  acceptance("knowledge", "Tidy all sends the prompt like Tidy does", async () => {
    withAgent(true);
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Tidy all" }));
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith({
        agent: "claude_code",
        prompt: ALL_PROMPT,
        terminal: null,
      }),
    );
    // The all-collections prompt is asked for once, when the button is pressed.
    expect(api.getTidyHandoff).toHaveBeenCalledTimes(1);
    expect(openTerminal).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { name: "Knowledge" })).toBeInTheDocument();
  });

  test("with no managed agent Tidy all offers Copy prompt, which fetches the prompt", async () => {
    withAgent(false);
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(ALL_PROMPT));
    expect(openTerminal).not.toHaveBeenCalled();
  });
});
