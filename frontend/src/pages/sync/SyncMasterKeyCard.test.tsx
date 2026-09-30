// frontend/src/pages/sync/SyncMasterKeyCard.test.tsx
//
// Master-key export/import (spec vault-sync). Export is a link to Settings ›
// Security, which owns the passphrase-protected backup.
// Import reads a picked File with `file.text()` and POSTs the material from
// any host. Neither path names a host path the page typed.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render as rtlRender, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";

vi.mock("@/lib/hooks/useSync", () => ({
  useImportMasterKey: vi.fn(),
  useKeyFingerprint: vi.fn(),
}));
const { useImportMasterKey, useKeyFingerprint } = await import("@/lib/hooks/useSync");
const useImportMock = vi.mocked(useImportMasterKey);
const useFingerprintMock = vi.mocked(useKeyFingerprint);

const importMutate = vi.fn();

const render = (ui: ReactElement) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>);

/** Stub the import mutation and the fingerprint query. */
function stub(opts: { importError?: unknown } = {}) {
  importMutate.mockImplementation((_material, handlers) => {
    if (opts.importError) return;
    handlers?.onSuccess?.({ locked_refs: [] });
  });
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

  test("export links to Settings › Security, which owns the key backup", () => {
    stub();
    render(<SyncMasterKeyCard />);

    expect(screen.getByRole("link", { name: /^export key$/i })).toHaveAttribute(
      "href",
      "/settings/security",
    );
    expect(screen.queryByRole("button", { name: /^export key$/i })).not.toBeInTheDocument();
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

  test("an imported key that still leaves references locked says so", async () => {
    stub();
    importMutate.mockImplementation((_material, handlers) =>
      handlers?.onSuccess?.({ locked_refs: ["github.TOKEN", "openai.KEY"] }),
    );
    render(<SyncMasterKeyCard />);

    await importFile("FERNET-KEY-MATERIAL");

    expect(await screen.findByRole("status")).toHaveTextContent(/2 secret/i);
  });
});
