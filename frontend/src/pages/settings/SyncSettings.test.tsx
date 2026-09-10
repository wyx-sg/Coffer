// frontend/src/pages/settings/SyncSettings.test.tsx
//
// Settings → Sync is a composition of exactly two cards after spec 010's
// rewrite: export/import and the master key. This guards the composition — the
// cards' own behaviour is covered by SyncBundleCard.test.tsx and
// SyncMasterKeyCard.test.tsx — and that the withdrawn continuous-sync controls
// (remote, auto-sync, sync-now, machine list) are gone.
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
}));

afterEach(() => vi.clearAllMocks());

describe("SyncSettings", () => {
  test("renders the export/import card and the master-key card", () => {
    render(<SyncSettings />);
    expect(screen.getByRole("button", { name: /export vault/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import vault/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export key/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import key/i })).toBeInTheDocument();
    expect(screen.getByTestId("key-fingerprint")).toBeInTheDocument();
  });

  test("carries none of the withdrawn continuous-sync controls", () => {
    render(<SyncSettings />);
    expect(screen.queryByText(/git remote/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/auto-sync/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sync now/i })).not.toBeInTheDocument();
    // The machine registry card is gone with the registry itself.
    expect(screen.queryByText(/^Machines$/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/machine name/i)).not.toBeInTheDocument();
  });
});
