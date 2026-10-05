// frontend/src/components/history/VaultHistoryView.test.tsx
//
// A History tab over one vault file (spec web-ui "Show a vault file's history on
// a History tab"): the versions newest first with their writers, the chosen
// version's diff against the one before it or the current content, Restore this
// version… asking first and keeping a refusal in its dialog, and a history that
// cannot be read as one Load error row. Mocked only at the network boundary.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

import { VaultHistoryView } from "./VaultHistoryView";

vi.mock("@/lib/api/vault", () => ({
  vaultApi: { history: vi.fn(), diff: vi.fn(), restore: vi.fn() },
}));

const { vaultApi } = await import("@/lib/api/vault");

const PATH = "knowledge/notes/cache.md";
const NOW = "c".repeat(40);
const AGENT = "b".repeat(40);
const FIRST = "a".repeat(40);

function version(sha: string, display_writer: string, status: string, added = 1, removed = 0) {
  return {
    version: sha,
    time: "2026-09-20T10:00:00Z",
    writer: display_writer.split(":")[0],
    display_writer,
    actor: null,
    machine: null,
    summary: "",
    operation: "edit",
    restored_from: null,
    removed: false,
    paths: [{ path: PATH, status, added, removed }],
  };
}

function renderView() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <VaultHistoryView path={PATH} storageKey="test-history" />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(vaultApi.history).mockResolvedValue({
    path: PATH,
    versions: [
      version(NOW, "disk", "modified", 2, 1),
      version(AGENT, "agent:claude-code", "modified"),
      version(FIRST, "user", "added", 3),
    ],
    next_cursor: null,
  });
  vi.mocked(vaultApi.diff).mockImplementation(async (path, sha, against) => ({
    path,
    version: sha,
    against,
    files: [
      {
        path: PATH,
        status: "modified",
        diff: `@@ -1 +1 @@\n-${against} before\n+${against} after ${sha.slice(0, 1)}\n`,
        added: 1,
        removed: 1,
      },
    ],
  }));
});
afterEach(() => vi.clearAllMocks());

acceptance(
  "web-ui",
  "the history tab lists versions with their writers and restores one",
  async () => {
    vi.mocked(vaultApi.restore).mockResolvedValue({
      path: PATH,
      version: "d".repeat(40),
      restored_from: FIRST,
      paths: [PATH],
    });
    renderView();
    const list = await screen.findByRole("list", { name: "Versions" });
    const rows = within(list).getAllByRole("button");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringMatching(/^Edited.*Current.*Edited on disk.*\+2 −1$/),
      expect.stringMatching(/^Edited.*Claude Code/),
      expect.stringMatching(/^Created.*You/),
    ]);
    // The newest is chosen with what it changed, and offers no restore.
    const panel = screen.getByRole("region", { name: "The chosen version" });
    expect(await within(panel).findByText("previous after c")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Restore this version…" })).toBeNull();

    // An older version: its own changes, then the file against how it is now.
    fireEvent.click(rows[2]);
    const older = screen.getByRole("region", { name: "The chosen version" });
    expect(await within(older).findByText("previous after a")).toBeInTheDocument();
    fireEvent.click(within(older).getByRole("button", { name: "Compare with current" }));
    expect(await within(older).findByText("current after a")).toBeInTheDocument();

    fireEvent.click(within(older).getByRole("button", { name: "Restore this version…" }));
    const dialog = await screen.findByRole("dialog", { name: "Restore this version?" });
    expect(dialog).toHaveTextContent("as a new version");
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore" }));
    await waitFor(() =>
      expect(vaultApi.restore).toHaveBeenCalledWith({
        path: PATH,
        version: FIRST,
        expected_current: NOW,
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // The history is read again, so the restore shows as the newest version.
    await waitFor(() => expect(vaultApi.history).toHaveBeenCalledTimes(2));
  },
);

describe("VaultHistoryView", () => {
  test("a restore refused because the file changed stays in its dialog", async () => {
    vi.mocked(vaultApi.restore).mockRejectedValue(
      new ApiError("VAULT_FILE_STALE", "changed since its history was read"),
    );
    renderView();
    const list = await screen.findByRole("list", { name: "Versions" });
    fireEvent.click(within(list).getAllByRole("button")[1]);
    fireEvent.click(await screen.findByRole("button", { name: "Restore this version…" }));
    const dialog = await screen.findByRole("dialog", { name: "Restore this version?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore" }));
    expect(await within(dialog).findByText("Couldn’t restore this version")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  test("a file with no recorded version says so", async () => {
    vi.mocked(vaultApi.history).mockResolvedValue({ path: PATH, versions: [], next_cursor: null });
    renderView();
    expect(await screen.findByText("No versions yet")).toBeInTheDocument();
  });
});

acceptance("web-ui", "a history that fails to load says so in its tab", async () => {
  vi.mocked(vaultApi.history).mockRejectedValueOnce(new ApiError("VAULT_GIT_FAILED", "git broke"));
  renderView();
  expect(await screen.findByText("Couldn’t read the history")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("list", { name: "Versions" })).toBeInTheDocument();
});
