// frontend/src/pages/sync/SyncPage.noRestore.test.tsx
//
// Restoring at a point in time stays a CLI operation: `--at` names a revision
// in the remote's history, which no route exposes, so a page could only offer
// a blind date box. This renders the real Runs and Setup tabs — a configured
// remote, a history with an applied round — and looks for any way to restore.
import { afterEach, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { RunRecord, SyncStatus } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncPage } from "./SyncPage";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncRuns: vi.fn(),
  useSyncStatus: vi.fn(),
  useRollbackRound: vi.fn(),
  useConfirmRound: vi.fn(),
  useRejectRound: vi.fn(),
  useRebuildFromRemote: vi.fn(),
  useSaveSyncRemote: vi.fn(),
  useRunConverge: vi.fn(),
  useExportMasterKey: vi.fn(),
  useImportMasterKey: vi.fn(),
  useKeyFingerprint: vi.fn(),
}));
vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: vi.fn(),
  useRenameSelf: vi.fn(),
  useRetireMachine: vi.fn(),
}));

const sync = await import("@/lib/hooks/useSync");
const machines = await import("@/lib/hooks/useMachines");

const idle = () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() });

const STATUS: SyncStatus = {
  configured: true,
  remote: {
    url: "https://git.example.com/me/vault.git",
    branch: "main",
    credential_ref: "sync.PUSH_TOKEN",
    include_credentials: false,
    interval_seconds: 3600,
    enabled: true,
    worktree_path: "/home/me/.coffer/sync",
  },
  last_run: null,
  machine_id: "a3f21c9e4b7d2610",
  machine_id_is_derived: true,
};

const APPLIED = {
  added: 1,
  modified: 0,
  deleted: 0,
  changes: [{ path: "knowledge/notes/a.md", status: "added" as const }],
};
const NONE = { added: 0, modified: 0, deleted: 0, changes: [] };

function round(id: number, over: Partial<RunRecord> = {}): RunRecord {
  return {
    id,
    started_at: "2026-09-13T09:00:00Z",
    finished_at: "2026-09-13T09:00:04Z",
    status: "ok",
    join: null,
    applied: NONE,
    published: NONE,
    commit: `c0ffee${id}`,
    conflicts: [],
    agent_resolved: [],
    failures: [],
    locked_refs: [],
    pending: null,
    error: null,
    ...over,
  };
}

function seed() {
  const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;
  m(sync.useSyncStatus).mockReturnValue({ data: STATUS, isPending: false });
  m(sync.useSyncRuns).mockReturnValue({
    data: { runs: [round(3, { applied: APPLIED }), round(2, { status: "no_change" })] },
    isLoading: false,
    error: null,
  });
  for (const hook of [
    sync.useRollbackRound,
    sync.useConfirmRound,
    sync.useRejectRound,
    sync.useRebuildFromRemote,
    sync.useSaveSyncRemote,
    sync.useRunConverge,
    sync.useExportMasterKey,
    sync.useImportMasterKey,
    machines.useRenameSelf,
    machines.useRetireMachine,
  ]) {
    m(hook).mockReturnValue(idle());
  }
  m(sync.useKeyFingerprint).mockReturnValue({ data: { fingerprint: "abc123def456" } });
  m(machines.useMachines).mockReturnValue({ data: { machines: [] }, isPending: false });
}

/** Any control that could restore, or ask when to restore to. */
function assertNoRestore() {
  expect(screen.queryAllByRole("button", { name: /restore/i })).toHaveLength(0);
  expect(screen.queryAllByRole("link", { name: /restore/i })).toHaveLength(0);
  expect(screen.queryAllByRole("menuitem", { name: /restore/i })).toHaveLength(0);
  expect(
    document.querySelectorAll('input[type="date"], input[type="datetime-local"]'),
  ).toHaveLength(0);
}

afterEach(() => vi.clearAllMocks());

acceptance("vault-sync", "no page offers a point-in-time restore", () => {
  seed();
  const view = render(
    <MemoryRouter initialEntries={["/sync"]}>
      <SyncPage />
    </MemoryRouter>,
  );
  // Runs, with the applied round opened too.
  expect(screen.getByText("c0ffee3")).toBeInTheDocument();
  assertNoRestore();
  fireEvent.click(screen.getAllByRole("row")[1]);
  assertNoRestore();
  view.unmount();

  // Setup: the remote, the master key and the machines.
  render(
    <MemoryRouter initialEntries={["/sync?tab=setup"]}>
      <SyncPage />
    </MemoryRouter>,
  );
  expect(screen.getByDisplayValue("https://git.example.com/me/vault.git")).toBeInTheDocument();
  assertNoRestore();
});
