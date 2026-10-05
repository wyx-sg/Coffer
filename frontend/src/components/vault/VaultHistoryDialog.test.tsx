// src/components/vault/VaultHistoryDialog.test.tsx — the History… dialog: the path in the
// vault, an optional time, Copy git command, Reveal in Finder and the hand-off split button.
// It lists no versions and restores nothing itself.
//
// Real QueryClientProvider and toast; the vault, fs and agent-providers apis are mocked.
import { acceptance } from "@/test/acceptance";
import { afterEach, beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { VaultHistoryDialog } from "./VaultHistoryDialog";

vi.mock("@/lib/api/vault", () => ({ vaultApi: { historyHandoff: vi.fn() } }));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/api/fs", () => ({
  fsApi: { listTerminals: vi.fn(), openTerminal: vi.fn(), reveal: vi.fn() },
}));
const { vaultApi } = await import("@/lib/api/vault");
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const { fsApi } = await import("@/lib/api/fs");

const PATH = "knowledge/notes/plan.md";
const VAULT = "/Users/me/.coffer/vault";
const served = (at: string | null) => ({
  path: PATH,
  absolute_path: `${VAULT}/${PATH}`,
  vault_path: VAULT,
  log_command: `git -C ${VAULT} log -p -- ${PATH}`,
  handoff: { prompt: at ? `Restore ${PATH} to how it was at ${at}.` : `Restore ${PATH}.` },
});

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  vi.mocked(vaultApi.historyHandoff).mockImplementation(async (_path, at) => served(at ?? null));
  vi.mocked(agentProvidersApi.list).mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
  } as never);
  vi.mocked(fsApi.listTerminals).mockResolvedValue([]);
  vi.mocked(fsApi.openTerminal).mockResolvedValue(undefined);
  vi.mocked(fsApi.reveal).mockResolvedValue(undefined);
});
afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <VaultHistoryDialog open onOpenChange={() => {}} path={PATH} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("VaultHistoryDialog", () => {
  acceptance(
    "web-ui",
    "a document's history dialog copies the git command and hands the restore off",
    async () => {
      renderDialog();
      expect(screen.getByTestId("vault-history-path")).toHaveTextContent(PATH);

      const copy = screen.getByRole("button", { name: "Copy git command" });
      await waitFor(() => expect(copy).toBeEnabled());
      fireEvent.click(copy);
      await waitFor(() =>
        expect(writeText).toHaveBeenCalledWith(`git -C ${VAULT} log -p -- ${PATH}`),
      );
      expect(await screen.findByText("Copied")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Reveal in Finder" }));
      await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(`${VAULT}/${PATH}`));

      // A picked time is what the hand-off asks the daemon about.
      fireEvent.change(screen.getByLabelText("Restore to how it was on"), {
        target: { value: "2026-09-01T10:30" },
      });
      const at = new Date("2026-09-01T10:30").toISOString();
      fireEvent.click(
        await screen.findByRole("button", { name: "Hand off to Claude Code to restore" }),
      );
      await waitFor(() =>
        expect(fsApi.openTerminal).toHaveBeenCalledWith({
          agent: "claude_code",
          prompt: `Restore ${PATH} to how it was at ${at}.`,
          terminal: null,
        }),
      );
      expect(vaultApi.historyHandoff).toHaveBeenLastCalledWith(PATH, at);

      // No versions, no diff, no restore of its own.
      expect(screen.queryByRole("button", { name: /^Restore/ })).toBeNull();
      expect(screen.queryByRole("list")).toBeNull();
    },
  );
});
