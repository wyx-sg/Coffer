// frontend/src/pages/settings/SyncSettings.test.tsx
//
// Settings → Sync is a composition of exactly three cards: export/import, the
// backup remote, and the master key. This guards the composition — each card's
// own behaviour is covered by its own test file — and that the withdrawn
// continuous-sync controls are still gone.
//
// "A remote" is no longer among the withdrawn things: spec vault-export-import
// ``## Backup`` brings one back deliberately, as a one-way backup destination.
// What stays withdrawn is convergence — syncing *from* a remote on a schedule,
// and the machine registry that arbitration needed.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { SyncSettings } from "./SyncSettings";

vi.mock("@/lib/filePicker", () => ({ pickDirectory: vi.fn() }));

vi.mock("@/lib/hooks/useSync", () => ({
  useExportVault: vi.fn(() => ({ mutate: vi.fn(), isPending: false, data: undefined })),
  useImportVault: vi.fn(() => ({ mutate: vi.fn(), isPending: false, data: undefined })),
  useExportMasterKey: vi.fn(() => ({ mutate: vi.fn(), isPending: false, data: undefined })),
  useImportMasterKey: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useKeyFingerprint: vi.fn(() => ({ data: { present: true, fingerprint: "abc123" } })),
  useBackupRemote: vi.fn(() => ({ data: { configured: false, remote: null }, isLoading: false })),
  useBackupStatus: vi.fn(() => ({
    data: { configured: false, remote: null, last_run: null },
    isLoading: false,
  })),
  useSaveBackupRemote: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
  useClearBackupRemote: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
  useRunBackupNow: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
}));

afterEach(() => vi.clearAllMocks());

describe("SyncSettings", () => {
  test("renders the export/import, backup and master-key cards", () => {
    render(<SyncSettings />);
    expect(screen.getByRole("button", { name: /export vault/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import vault/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /back up now/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export key/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import key/i })).toBeInTheDocument();
    expect(screen.getByTestId("key-fingerprint")).toBeInTheDocument();
  });

  test("carries none of the withdrawn convergence controls", () => {
    render(<SyncSettings />);
    // Pulling from a remote on a schedule is what was withdrawn; pushing to one
    // is what this page now offers.
    expect(screen.queryByText(/auto-sync/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sync now/i })).not.toBeInTheDocument();
    // The machine registry card is gone with the registry itself.
    expect(screen.queryByText(/^Machines$/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/machine name/i)).not.toBeInTheDocument();
  });

  test("offers no field that could hold a secret", () => {
    // The backup remote names its push credential by reference. A password
    // field appearing on this page would mean that rule had been broken.
    render(<SyncSettings />);
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0);
  });
});
