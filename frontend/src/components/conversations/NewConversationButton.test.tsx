// NewConversationButton.test.tsx — spec chat "Start a new conversation in the
// terminal". The newConversation.* strings are not in the locale files yet (the
// main session merges the scratchpad's newconv-i18n.json), so the test loads them.
import { beforeAll, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { NewConversationButton } from "./NewConversationButton";
import i18n from "@/i18n";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/fs", () => ({
  fsApi: { listTerminals: vi.fn(), openTerminal: vi.fn(), browse: vi.fn(), pickFolder: vi.fn() },
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const { fsApi } = await import("@/lib/api/fs");
const { useAgents } = await import("@/lib/hooks/useAgents");
const openTerminal = vi.mocked(fsApi.openTerminal);

const agent = (type: string, name: string) => ({ uid: `u-${type}`, type, display_name: name });

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      newConversation: {
        button: "New conversation",
        noAgent: "No managed agent yet.",
        title: "New conversation",
        description: "Starts a blank session.",
        agent: "Agent",
        directory: "Working directory",
        directoryHint: "Defaults to the workspace.",
        workspacePlaceholder: "~/.coffer/content/workspace",
        openIn: "Open in {{terminal}}",
        moreTerminals: "Open in another terminal",
      },
    },
    true,
    true,
  );
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem("coffer.preferredTerminal", "iterm");
  vi.mocked(fsApi.listTerminals).mockResolvedValue([{ value: "iterm", label: "iTerm" }] as never);
  openTerminal.mockResolvedValue(undefined);
  vi.mocked(useAgents).mockReturnValue({
    data: [agent("claude_code", "Claude Code"), agent("codex", "Codex")],
  } as never);
});

function renderButton(agentKey?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <NewConversationButton agentKey={agentKey} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("NewConversationButton", () => {
  acceptance(
    "chat",
    "New conversation starts the chosen agent in the chosen directory",
    async () => {
      localStorage.setItem("coffer.newConversationAgent", "codex");
      renderButton();
      fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
      expect(await screen.findByRole("combobox", { name: "Agent" })).toHaveTextContent("Codex");
      fireEvent.change(screen.getByLabelText("Working directory"), {
        target: { value: "/work/api" },
      });
      fireEvent.click(await screen.findByRole("button", { name: "Open in iTerm" }));
      await waitFor(() =>
        expect(openTerminal).toHaveBeenCalledWith({
          agent: "codex",
          cwd: "/work/api",
          terminal: "iterm",
        }),
      );
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    },
  );

  acceptance("chat", "a refused start keeps the dialog open", async () => {
    openTerminal.mockRejectedValue(new ApiError("terminal_failed", "no terminal here"));
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    fireEvent.click(await screen.findByRole("button", { name: "Open in iTerm" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  acceptance(
    "agent-registry",
    "New conversation on the Sessions tab starts this agent",
    async () => {
      renderButton("codex");
      fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
      fireEvent.click(await screen.findByRole("button", { name: "Open in iTerm" }));
      await waitFor(() =>
        expect(openTerminal).toHaveBeenCalledWith(expect.objectContaining({ agent: "codex" })),
      );
    },
  );

  test("is disabled with no managed agent", () => {
    vi.mocked(useAgents).mockReturnValue({ data: [] } as never);
    renderButton();
    expect(screen.getByRole("button", { name: "New conversation" })).toBeDisabled();
  });
});
