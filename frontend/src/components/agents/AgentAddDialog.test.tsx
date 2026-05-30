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
  display_name: "OpenAI Codex",
  config_dir: "/home/u/.codex",
  default_skill_dir: "/home/u/.codex/skills",
  suggested_name: "codex",
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

  test("shows the empty message when nothing new is found", () => {
    stub({ data: [] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    expect(screen.getByText(/no new agents found/i)).toBeInTheDocument();
  });

  test("adding the selected candidate registers it and reports success", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    stub({ data: [CODEX], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={onCreated} />);

    fireEvent.click(screen.getByRole("button", { name: /add selected/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({ type: "codex", name: "codex" });
    // Result view lists what was added + onCreated refreshes the agents list.
    await waitFor(() => expect(screen.getByText(/added:/i)).toBeInTheDocument());
    expect(screen.getByText("codex")).toBeInTheDocument();
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

describe("AgentAddDialog — manual section", () => {
  test("the manual form is hidden until the disclosure is expanded", () => {
    stub({ data: [] });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);
    // Register button (manual submit) is not in the DOM until revealed.
    expect(screen.queryByRole("button", { name: /^register$/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    expect(screen.getByRole("button", { name: /^register$/i })).toBeInTheDocument();
  });

  test("submitting the manual form registers with the typed name", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    stub({ data: [], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={onCreated} />);

    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "my-codex" } });
    fireEvent.click(screen.getByRole("button", { name: /^register$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const body = mutateAsync.mock.calls[0][0];
    expect(body.name).toBe("my-codex");
    // Default type the form pre-selects is "claude_code".
    expect(body.type).toBe("claude_code");
    expect(onCreated).toHaveBeenCalled();
  });

  test("a blank manual name is submitted as null", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    stub({ data: [], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    fireEvent.click(screen.getByRole("button", { name: /^register$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const body = mutateAsync.mock.calls[0][0];
    expect(body.name).toBeNull();
    expect(body.type).toBe("claude_code");
  });
});

describe("AgentAddDialog — register errors", () => {
  test("a config-dir-registered error renders inline when adding a candidate", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new ApiError("AGENT_CONFIG_DIR_REGISTERED", "already registered"));
    stub({ data: [CODEX], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /add selected/i }));

    await waitFor(() => expect(screen.getByText(/already registered/i)).toBeInTheDocument());
  });

  test("a register error from the manual form renders inline", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new ApiError("AGENT_CONFIG_DIR_REGISTERED", "already registered"));
    stub({ data: [], mutateAsync });
    renderDialog(<AgentAddDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
    fireEvent.click(screen.getByRole("button", { name: /^register$/i }));

    await waitFor(() => expect(screen.getByText(/already registered/i)).toBeInTheDocument());
  });
});
