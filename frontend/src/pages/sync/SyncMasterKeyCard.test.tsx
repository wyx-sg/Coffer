// frontend/src/pages/sync/SyncMasterKeyCard.test.tsx
//
// Master-key export/import (spec vault-sync). Export runs only in the desktop
// app: the shell checks presence and writes the backup itself, and the card
// shows where it went; a browser gets "Open in Coffer app" in its place.
// Import reads a picked File with `file.text()` and POSTs the material from
// any host. Neither path names a host path the page typed.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";

vi.mock("@/lib/hooks/useSync", () => ({
  useExportMasterKeyBackup: vi.fn(),
  useImportMasterKey: vi.fn(),
  useKeyFingerprint: vi.fn(),
}));
let inShell = false;
vi.mock("@/lib/tauri", () => ({ presenceAvailable: () => inShell }));
const { useExportMasterKeyBackup, useImportMasterKey, useKeyFingerprint } =
  await import("@/lib/hooks/useSync");
const useExportMock = vi.mocked(useExportMasterKeyBackup);
const useImportMock = vi.mocked(useImportMasterKey);
const useFingerprintMock = vi.mocked(useKeyFingerprint);

const exportMutate = vi.fn();
const importMutate = vi.fn();

const BACKUP = { path: "/Users/me/Backups/coffer-master.key", fingerprint: "abc123def456" };

/** Stub both mutations. `exportResult` is what a successful backup returns. */
function stub(
  opts: {
    exportResult?: { path: string; fingerprint: string };
    exportError?: unknown;
    importError?: unknown;
  } = {},
) {
  exportMutate.mockImplementation((_vars, handlers) => {
    if (opts.exportError) return;
    handlers?.onSuccess?.(opts.exportResult ?? BACKUP);
  });
  importMutate.mockImplementation((_material, handlers) => {
    if (opts.importError) return;
    handlers?.onSuccess?.({ locked_refs: [] });
  });
  useExportMock.mockReturnValue({
    mutate: exportMutate,
    isPending: false,
    error: opts.exportError ?? null,
  } as unknown as ReturnType<typeof useExportMasterKeyBackup>);
  useImportMock.mockReturnValue({
    mutate: importMutate,
    isPending: false,
    error: opts.importError ?? null,
  } as unknown as ReturnType<typeof useImportMasterKey>);
  useFingerprintMock.mockReturnValue({
    data: { fingerprint: "abc123def456" },
  } as unknown as ReturnType<typeof useKeyFingerprint>);
}

afterEach(() => {
  inShell = false;
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

/** A File whose text() resolves to `content` (jsdom's File lacks text()). */
function keyFile(content: string, name = "coffer-master.key"): File {
  const file = new File([content], name);
  Object.defineProperty(file, "text", { value: () => Promise.resolve(content) });
  return file;
}

/** Pick a key file, then confirm the replacement the dialog asks about. */
async function importFile(content: string) {
  fireEvent.change(screen.getByLabelText(/import key/i), {
    target: { files: [keyFile(content)] },
  });
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent(/replace this machine's master key\?/i);
  fireEvent.click(within(dialog).getByRole("button", { name: /import key/i }));
}

describe("SyncMasterKeyCard", () => {
  test("shows no typed-path field — the browser never needs a host path", () => {
    stub();
    render(<SyncMasterKeyCard />);
    expect(screen.queryByLabelText(/key file path/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("key-fingerprint")).toBeInTheDocument();
  });

  test("in the desktop app, export writes a backup through the shell and says where", async () => {
    inShell = true;
    stub();
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /^export key$/i }));

    expect(exportMutate).toHaveBeenCalled();
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(BACKUP.path);
    expect(status).toHaveTextContent(BACKUP.fingerprint);
  });

  test("in a browser, export is replaced by Open in Coffer app", () => {
    stub();
    render(<SyncMasterKeyCard />);

    expect(screen.queryByRole("button", { name: /^export key$/i })).not.toBeInTheDocument();
    const inApp = screen.getByRole("button", { name: /open in coffer app/i });
    expect(inApp).toBeDisabled();
    fireEvent.click(inApp);
    expect(exportMutate).not.toHaveBeenCalled();
  });

  test("import reads the picked file's contents, confirms, then posts the material", async () => {
    stub();
    render(<SyncMasterKeyCard />);

    await importFile("  FERNET-KEY-MATERIAL\n");

    // The material is trimmed; no path is ever passed.
    await waitFor(() =>
      expect(importMutate).toHaveBeenCalledWith("FERNET-KEY-MATERIAL", expect.anything()),
    );
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  test("cancelling the confirmation posts nothing", async () => {
    stub();
    render(<SyncMasterKeyCard />);

    fireEvent.change(screen.getByLabelText(/import key/i), {
      target: { files: [keyFile("FERNET-KEY-MATERIAL")] },
    });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(importMutate).not.toHaveBeenCalled();
  });

  test("clicking Import key opens the file input rather than mutating", () => {
    stub();
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /import key/i }));

    expect(click).toHaveBeenCalledTimes(1);
    expect(importMutate).not.toHaveBeenCalled();
  });

  test("a cancelled file picker mutates nothing", async () => {
    stub();
    render(<SyncMasterKeyCard />);

    fireEvent.change(screen.getByLabelText(/import key/i), { target: { files: [] } });

    await waitFor(() => expect(importMutate).not.toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("an empty key file is rejected in the browser, before the daemon sees it", async () => {
    stub();
    render(<SyncMasterKeyCard />);

    fireEvent.change(screen.getByLabelText(/import key/i), {
      target: { files: [keyFile("   \n")] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(/empty/i);
    expect(importMutate).not.toHaveBeenCalled();
  });

  // Transport failures are reported by the hook's onError toast (the house
  // default), so the card claims no success rather than growing a second
  // error surface of its own.
  test("a server rejection of the key material claims nothing succeeded", async () => {
    stub({ importError: new ApiError("MASTER_KEY_FILE_INVALID", "not a valid Fernet key") });
    render(<SyncMasterKeyCard />);

    await importFile("BAD-KEY");

    await waitFor(() => expect(importMutate).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("a failed or cancelled backup claims nothing", () => {
    inShell = true;
    stub({ exportError: new Error("presence check cancelled") });
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /^export key$/i }));

    expect(exportMutate).toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("an imported key that still leaves references locked says so", async () => {
    stub();
    importMutate.mockImplementation((_material, handlers) =>
      handlers?.onSuccess?.({ locked_refs: ["github.TOKEN", "openai.KEY"] }),
    );
    render(<SyncMasterKeyCard />);

    await importFile("FERNET-KEY-MATERIAL");

    expect(await screen.findByRole("status")).toHaveTextContent(/2 credential/i);
  });
});
