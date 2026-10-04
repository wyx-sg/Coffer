// src/components/handoff/AgentHandoff.test.tsx — the hand-off split button: the main part
// starts the hand-off agent in the preferred terminal with the prompt sent, the ▾ menu
// holds the other managed agent and Copy prompt.
//
// Real QueryClientProvider and toast; the agent-providers and fs apis are mocked.
import { acceptance } from "@/test/acceptance";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import { AgentHandoff } from "./AgentHandoff";

vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/api/fs", () => ({
  fsApi: { listTerminals: vi.fn(), openTerminal: vi.fn() },
}));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const { fsApi } = await import("@/lib/api/fs");
const listAgents = vi.mocked(agentProvidersApi.list);
const openTerminal = vi.mocked(fsApi.openTerminal);
const listTerminals = vi.mocked(fsApi.listTerminals);

const PROMPT = "Install jq 1.6 or newer on this machine.";
const CLAUDE = { agent_key: "claude_code", display_name: "Claude Code" };
const CODEX = { agent_key: "codex", display_name: "Codex" };

type Props = Partial<React.ComponentProps<typeof AgentHandoff>>;

/** `managed`: the agent keys that are available; every other known agent is not installed. */
function renderHandoff(managed: string[], props: Props = {}) {
  listAgents.mockResolvedValue({
    agents: [CLAUDE, CODEX].map((a) => ({ ...a, available: managed.includes(a.agent_key) })),
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <AgentHandoff prompt={PROMPT} {...props} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  openTerminal.mockResolvedValue(undefined);
  listTerminals.mockResolvedValue([{ label: "iTerm", value: "iterm" }]);
});
afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

const openMenu = async () => {
  fireEvent.click(await screen.findByRole("button", { name: "More options" }));
  return screen.findByRole("menu");
};

describe("AgentHandoff", () => {
  acceptance("web-ui", "the split button hands a prompt over or copies it", async () => {
    renderHandoff(["claude_code"]);
    fireEvent.click(await screen.findByRole("button", { name: "Hand off to Claude Code" }));
    // No confirmation: the daemon is asked straight away, in the system terminal.
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith({
        agent: "claude_code",
        prompt: PROMPT,
        terminal: null,
      }),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText("Opened in System terminal")).toBeInTheDocument();
    expect(writeText).not.toHaveBeenCalled();

    // The menu copies the prompt as given; with one managed agent it holds Copy prompt alone.
    const menu = await openMenu();
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(1);
    fireEvent.click(within(menu).getByRole("menuitem", { name: /^Copy prompt/ }));
    expect(writeText).toHaveBeenCalledWith(PROMPT);
    expect(await screen.findByText("Prompt copied")).toBeInTheDocument();
  });

  test("with no managed agent only a Copy prompt button is offered", async () => {
    renderHandoff([]);
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(PROMPT);
    expect(openTerminal).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Hand off/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "More options" })).toBeNull();
  });

  test("a terminal that fails to open is reported beside Copy prompt", async () => {
    openTerminal.mockRejectedValue(new ApiError("FS_TERMINAL_FAILED", "no terminal"));
    renderHandoff(["claude_code"]);
    fireEvent.click(await screen.findByRole("button", { name: "Hand off to Claude Code" }));
    // The refusal is reported in a toast beside Copy prompt, the way out.
    expect(await screen.findByText(/terminal couldn.t be started/i)).toBeInTheDocument();
    const toastCopy = await screen.findByRole("button", { name: "Copy prompt" });
    fireEvent.click(toastCopy);
    expect(writeText).toHaveBeenCalledWith(PROMPT);
  });

  acceptance("web-ui", "the menu offers the other managed agent", async () => {
    renderHandoff(["claude_code", "codex"]);
    const menu = await openMenu();
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringMatching(/^Hand off to Codex/),
      expect.stringMatching(/^Copy prompt/),
    ]);
    fireEvent.click(items[0]);
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith({
        agent: "codex",
        prompt: PROMPT,
        terminal: null,
      }),
    );
  });

  test("with Claude Code missing the button hands off to the other managed agent", async () => {
    // Claude Code's own program is gone: it cannot run its install prompt, Codex can.
    renderHandoff(["codex"]);
    fireEvent.click(await screen.findByRole("button", { name: "Hand off to Codex" }));
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith({
        agent: "codex",
        prompt: PROMPT,
        terminal: null,
      }),
    );
    const menu = await openMenu();
    expect(within(menu).queryByRole("menuitem", { name: /Hand off to Claude Code/ })).toBeNull();
  });

  test("the stored hand-off agent and preferred terminal decide the button and the request", async () => {
    localStorage.setItem("coffer.preferredTerminal", "iterm");
    localStorage.setItem("coffer.handoffAgent", "codex");
    renderHandoff(["claude_code", "codex"]);
    fireEvent.click(await screen.findByRole("button", { name: "Hand off to Codex" }));
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith({
        agent: "codex",
        prompt: PROMPT,
        terminal: "iterm",
      }),
    );
    expect(await screen.findByText("Opened in iTerm")).toBeInTheDocument();
    // Claude Code, no longer the default, is the menu's other agent.
    const menu = await openMenu();
    expect(within(menu).getByRole("menuitem", { name: /^Hand off to Claude Code/ })).toBeVisible();
  });

  acceptance(
    "web-ui",
    "an unavailable hand-off agent falls back to the first managed one",
    async () => {
      localStorage.setItem("coffer.handoffAgent", "codex");
      renderHandoff(["claude_code"]);
      expect(await screen.findByRole("button", { name: "Hand off to Claude Code" })).toBeVisible();
      expect(screen.queryByRole("button", { name: "Hand off to Codex" })).toBeNull();
    },
  );

  test("a prompt that is a request is made when the verb is picked, told which agent", async () => {
    const request = vi.fn(() => Promise.resolve("asked for"));
    renderHandoff(["claude_code"], { prompt: request });
    await waitFor(() => expect(listAgents).toHaveBeenCalled());
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Hand off to Claude Code" }));
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith({
        agent: "claude_code",
        prompt: "asked for",
        terminal: null,
      }),
    );
    expect(request).toHaveBeenCalledWith({ agent: "Claude Code" });

    const menu = await openMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /^Copy prompt/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("asked for"));
    expect(request).toHaveBeenLastCalledWith({ agent: null });
  });

  test("a button with a label keeps its name and still hands off", async () => {
    renderHandoff(["claude_code"], { label: "Tidy" });
    fireEvent.click(await screen.findByRole("button", { name: "Tidy" }));
    await waitFor(() => expect(openTerminal).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("button", { name: "Hand off to Claude Code" })).toBeNull();
  });

  test("the main part names the terminal in its tooltip", async () => {
    renderHandoff(["claude_code"]);
    const main = await screen.findByRole("button", { name: "Hand off to Claude Code" });
    act(() => main.focus());
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Start Claude Code in System terminal to handle this",
    );
  });
});
