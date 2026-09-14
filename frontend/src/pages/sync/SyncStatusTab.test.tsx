// frontend/src/pages/sync/SyncStatusTab.test.tsx
//
// What Status must make impossible to miss: a conflict that stopped the round,
// and a round the deletion guard held. Both are banners above everything else,
// and the held round's DIRECTION decides what the user is being asked — which
// is the difference between "another machine deleted a lot" and "this machine
// is about to erase everyone else's vault".
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";

import type { ConvergeRound, PendingConfirmation, SyncStatus } from "@/lib/api/sync";
import { SyncStatusTab } from "./SyncStatusTab";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: vi.fn(),
  useSaveSyncRemote: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRunConverge: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useConfirmRound: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRejectRound: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRebuildFromRemote: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useKeyFingerprint: vi.fn(() => ({ data: { fingerprint: "abc123" } })),
  useExportMasterKey: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useImportMasterKey: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const { useSyncStatus, useConfirmRound, useRejectRound } = await import("@/lib/hooks/useSync");

const NO_COUNTS = { added: 0, modified: 0, deleted: 0 };

function round(overrides: Partial<ConvergeRound> = {}): ConvergeRound {
  return {
    status: "ok",
    join: null,
    applied: NO_COUNTS,
    published: NO_COUNTS,
    commit: null,
    conflicts: [],
    agent_resolved: [],
    failures: [],
    locked_refs: [],
    pending: null,
    error: null,
    ...overrides,
  };
}

function pending(direction: "apply" | "publish"): PendingConfirmation {
  return {
    direction,
    breaches: [{ area: "knowledge", deleted: 41, total: 90 }],
    paths: ["knowledge/notes/a.md", "knowledge/notes/b.md"],
    raised_at: "2026-09-13T09:00:00Z",
  };
}

function seed(last_run: ConvergeRound | null, isPending = false) {
  const status: SyncStatus = {
    configured: true,
    remote: {
      url: "https://git.example.com/me/vault.git",
      branch: "main",
      credential_ref: "sync.PUSH_TOKEN",
      include_credentials: true,
      interval_seconds: 3600,
      enabled: true,
      worktree_path: "/home/me/.coffer/sync",
    },
    last_run,
    machine_id: "a3f21c9e4b7d2610",
    machine_id_is_derived: true,
  };
  vi.mocked(useSyncStatus).mockReturnValue({
    data: isPending ? undefined : status,
    isPending,
  } as unknown as ReturnType<typeof useSyncStatus>);
}

afterEach(() => vi.clearAllMocks());

describe("SyncStatusTab", () => {
  test("a clean round shows neither banner", () => {
    seed(round());
    render(<SyncStatusTab />);
    expect(screen.queryByTestId("sync-conflict-banner")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sync-pending-banner")).not.toBeInTheDocument();
  });

  test("a conflict names the paths and the working tree that holds them", () => {
    seed(round({ status: "conflict", conflicts: ["knowledge/notes/plan.md"] }));
    render(<SyncStatusTab />);

    const banner = screen.getByTestId("sync-conflict-banner");
    expect(banner).toHaveTextContent("knowledge/notes/plan.md");
    expect(banner).toHaveTextContent("/home/me/.coffer/sync");
    // The resolution is the user's, with their own git.
    expect(banner).toHaveTextContent(/git tools/i);
  });

  test("a held apply round says the remote would delete this vault's documents", () => {
    seed(round({ status: "awaiting_confirmation", pending: pending("apply") }));
    render(<SyncStatusTab />);

    const banner = screen.getByTestId("sync-pending-banner");
    expect(banner).toHaveTextContent(/would delete a large part of this vault/i);
    expect(banner).toHaveTextContent("41");
    expect(banner).toHaveTextContent("knowledge/notes/a.md");
    // The reinstall warning belongs to the publish direction only.
    expect(banner).not.toHaveTextContent(/reinstalled/i);
  });

  test("a held publish round warns that Reject is the honest answer after a reinstall", () => {
    seed(round({ status: "awaiting_confirmation", pending: pending("publish") }));
    render(<SyncStatusTab />);

    const banner = screen.getByTestId("sync-pending-banner");
    expect(banner).toHaveTextContent(/would delete a large part of the remote/i);
    expect(banner).toHaveTextContent(/reinstalled, or restored from a backup/i);
    expect(banner).toHaveTextContent(/Reject/);
  });

  acceptance("vault-sync", "an oversized deletion is held for confirmation", () => {
    const confirmMutate = vi.fn();
    const rejectMutate = vi.fn();
    vi.mocked(useConfirmRound).mockReturnValue({
      mutate: confirmMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useConfirmRound>);
    vi.mocked(useRejectRound).mockReturnValue({
      mutate: rejectMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRejectRound>);
    seed(round({ status: "awaiting_confirmation", pending: pending("publish") }));
    render(<SyncStatusTab />);

    screen.getByRole("button", { name: /^confirm$/i }).click();
    expect(confirmMutate).toHaveBeenCalled();
    screen.getByRole("button", { name: /^reject$/i }).click();
    expect(rejectMutate).toHaveBeenCalled();
  });

  test("the round report carries what was applied, published, merged and locked", () => {
    seed(
      round({
        applied: { added: 3, modified: 1, deleted: 0 },
        published: { added: 0, modified: 2, deleted: 1 },
        commit: "abc1234",
        agent_resolved: ["knowledge/notes/merged.md"],
        failures: [{ path: "resources/agent/desktop.yaml", reason: "config_dir missing" }],
        locked_refs: ["github.TOKEN"],
        join: "returning",
      }),
    );
    render(<SyncStatusTab />);

    const report = screen.getByTestId("sync-last-round");
    expect(report).toHaveTextContent("abc1234");
    expect(report).toHaveTextContent(/returning machine/i);
    expect(screen.getByTestId("sync-agent-resolved")).toHaveTextContent(
      "knowledge/notes/merged.md",
    );
    expect(screen.getByTestId("sync-round-failures")).toHaveTextContent("config_dir missing");
    expect(screen.getByTestId("sync-locked-refs")).toHaveTextContent("github.TOKEN");
  });

  test("the master key lives here, next to what it decrypts", () => {
    seed(round());
    render(<SyncStatusTab />);
    expect(screen.getByRole("button", { name: /export key/i })).toBeInTheDocument();
    expect(screen.getByTestId("key-fingerprint")).toBeInTheDocument();
  });

  test("no field on this tab could hold a secret", () => {
    // The remote names its push credential by reference. A password field
    // appearing here would mean that rule had been broken.
    seed(round());
    render(<SyncStatusTab />);
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0);
  });
});
