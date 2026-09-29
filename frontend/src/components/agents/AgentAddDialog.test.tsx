// frontend/src/components/agents/AgentAddDialog.test.tsx
//
// The combined Add dialog folds the old detect dialog + manual add form into
// one surface: on open it auto-scans for installed-but-unregistered agents and
// lists them as a checklist (default all ticked), and behind an "Add manually"
// disclosure it reveals the manual registration form. Both paths register via
// useRegisterAgent and surface register errors inline. We mock the candidate
// query + register mutation to drive each state.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";
import { AgentAddDialog } from "./AgentAddDialog";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentCandidates: vi.fn(),
  useRegisterAgent: vi.fn(),
}));
const { useAgentCandidates, useRegisterAgent } = await import("@/lib/hooks/useAgents");
const useAgentCandidatesMock = vi.mocked(useAgentCandidates);
const useRegisterAgentMock = vi.mocked(useRegisterAgent);

// The manual section embeds a FolderPicker whose folder browser calls
// useQuery, so renders need a QueryClient even though the agent hooks are
// mocked.
function renderDialog(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

const CODEX = {
  type: "codex",
  name: "codex",
  display_name: "OpenAI Codex",
  config_dir: "/home/u/.codex",
  standard_config_dir: "/home/u/.codex",
  default_skill_dir: "/home/u/.codex/skills",
  state: "installed_active",
  version: "codex-cli 0.40.0",
  uid: null,
  addable: true,
  other_config_dir: null,
};

function stub(opts: {
  data?: unknown;
  isPending?: boolean;
  isError?: boolean;
  error?: unknown;
  mutateAsync?: ReturnType<typeof vi.fn>;
  registerError?: unknown;
}) {
  useAgentCandidatesMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    isError: opts.isError ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof useAgentCandidates>);
  useRegisterAgentMock.mockReturnValue({
    mutateAsync: opts.mutateAsync ?? vi.fn().mockResolvedValue({}),
    isPending: false,
    error: opts.registerError ?? null,
  } as unknown as ReturnType<typeof useRegisterAgent>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentAddDialog — detected section", () => {
  test("shows the scanning state while candidates load", () => {
    stub({ isPending: true });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    expect(screen.getByText(/scanning/i)).toBeInTheDocument();
  });

  test("lists discovered candidates for the user to choose", () => {
    stub({ data: [CODEX] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    expect(screen.getByText(/detected agents/i)).toBeInTheDocument();
    expect(screen.getByText(/found these agents/i)).toBeInTheDocument();
    expect(screen.getByText("OpenAI Codex")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.codex")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  test("shows the 'may already be added' message when agents are registered and none is new", () => {
    stub({ data: [] });
    renderDialog(
      <AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} hasRegisteredAgents />,
    );
    expect(screen.getByText(/no new agents found/i)).toBeInTheDocument();
  });

  test("on a first run with nothing detected, points at the manual form instead", () => {
    // Nothing is registered, so "they may already be added" would be wrong.
    stub({ data: [] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    expect(screen.getByText(/no agents were detected on this machine/i)).toBeInTheDocument();
    expect(screen.queryByText(/may already be added/i)).not.toBeInTheDocument();
  });

  test("the footer carries Cancel and the primary action in one row", () => {
    stub({ data: [CODEX] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    const cancel = screen.getByRole("button", { name: /cancel/i });
    const primary = screen.getByRole("button", { name: /add selected/i });
    expect(cancel.parentElement).toBe(primary.parentElement);
    // Opening the manual form swaps the primary for Register in the same slot.
    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    expect(screen.queryByRole("button", { name: /add selected/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^register$/i }).parentElement).toBe(
      cancel.parentElement,
    );
  });

  test("the manual form's type picker shows product names, not registry keys", () => {
    stub({ data: [] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    expect(screen.getByRole("combobox", { name: /type/i })).toHaveTextContent("Claude Code");
    expect(screen.queryByText("claude_code")).not.toBeInTheDocument();
  });

  test("adding the selected candidate registers it and reports success", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    stub({ data: [CODEX], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={onCreated} />);

    fireEvent.click(screen.getByRole("button", { name: /add selected/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({ type: "codex", config_dir: "/home/u/.codex" });
    // Result view lists what was added + onCreated refreshes the agents list.
    await waitFor(() => expect(screen.getByText(/added:/i)).toBeInTheDocument());
    expect(screen.getByText("OpenAI Codex")).toBeInTheDocument();
    expect(onCreated).toHaveBeenCalled();
  });

  test("deselecting all disables the add-selected button", () => {
    stub({ data: [CODEX] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    fireEvent.click(screen.getByRole("checkbox")); // uncheck
    expect(screen.getByRole("button", { name: /add selected/i })).toBeDisabled();
  });

  test("Cancel closes the dialog", () => {
    stub({ data: [CODEX] });
    const onOpenChange = vi.fn();
    renderDialog(<AgentAddDialog open onOpenChange={onOpenChange} onCreated={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe("AgentAddDialog — two-signal candidates", () => {
  // Installed but never run: addable — registering it creates the directory.
  const NEVER_RUN = {
    ...CODEX,
    type: "claude_code",
    name: "claude-code",
    display_name: "Claude Code",
    config_dir: "/home/u/.claude",
    standard_config_dir: "/home/u/.claude",
    default_skill_dir: "/home/u/.claude/skills",
    state: "installed_never_run",
    version: "2.0.1 (Claude Code)",
  };
  const CONFIG_ONLY = {
    ...CODEX,
    config_dir: "/home/u/.codex-old",
    state: "config_only",
    version: null,
    addable: false,
  };
  // A directory CLAUDE_CONFIG_DIR names in the daemon's environment.
  const ENV_NAMED = {
    ...NEVER_RUN,
    config_dir: "/home/u/claude-work",
    default_skill_dir: "/home/u/claude-work/skills",
    state: "installed_active",
    other_config_dir: "/home/u/.claude",
  };

  test("an installed-but-never-run candidate can be ticked; a config-only one says why", () => {
    stub({ data: [NEVER_RUN, CONFIG_ONLY] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    // One checkbox: the installed (never run) Claude Code.
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByText(/installed but never run/i)).toBeInTheDocument();
    expect(screen.getByText("Not installed")).toBeInTheDocument();
    // Versions ride beside the names.
    expect(screen.getByText("2.0.1 (Claude Code)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add selected \(1\)/i })).toBeEnabled();
  });

  test("with nothing addable there is no Add selected", () => {
    stub({ data: [CONFIG_ONLY] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add selected/i })).not.toBeInTheDocument();
  });

  test("an environment-named directory registers with its own config_dir", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    stub({ data: [CODEX, ENV_NAMED], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /add selected \(2\)/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(mutateAsync).toHaveBeenCalledWith({
      type: "claude_code",
      config_dir: "/home/u/claude-work",
    });
  });
});

describe("AgentAddDialog — manual section", () => {
  test("the manual form is hidden until the disclosure is expanded", () => {
    stub({ data: [] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    // Register button (manual submit) is not in the DOM until revealed.
    expect(screen.queryByRole("button", { name: /^register$/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    expect(screen.getByRole("button", { name: /^register$/i })).toBeInTheDocument();
  });

  test("submitting the manual form registers the chosen type with no name field", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    stub({ data: [], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={onCreated} />);

    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    // An agent is named by its type, so the form asks for no name.
    expect(screen.queryByLabelText(/^name$/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^register$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    // Default type the form pre-selects is "claude_code".
    expect(mutateAsync.mock.calls[0][0]).toEqual({ type: "claude_code", config_dir: null });
    expect(onCreated).toHaveBeenCalled();
  });
});

describe("AgentAddDialog — register errors", () => {
  test("a type-registered error renders inline when adding a candidate", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new ApiError("AGENT_TYPE_REGISTERED", "already registered"));
    stub({ data: [CODEX], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /add selected/i }));

    await waitFor(() => expect(screen.getByText(/already registered/i)).toBeInTheDocument());
  });

  test("a register error from the manual form renders inline", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new ApiError("AGENT_TYPE_REGISTERED", "already registered"));
    stub({ data: [], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    fireEvent.click(screen.getByRole("button", { name: /^register$/i }));

    await waitFor(() => expect(screen.getByText(/already registered/i)).toBeInTheDocument());
  });
});
