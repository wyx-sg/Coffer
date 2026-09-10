// frontend/src/pages/settings/SyncMasterKeyCard.test.tsx
//
// Master-key export/import (spec vault-export-import) through the browser's own file
// mechanisms. Export asks the daemon for the key material and saves it via a
// transient `<a download>`; import reads a picked File with `file.text()` and
// POSTs the material. Neither path names a host path, so there is no native
// dialog to mock and no typed-path fallback to reveal.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";

vi.mock("@/lib/hooks/useSync", () => ({
  useExportMasterKey: vi.fn(),
  useImportMasterKey: vi.fn(),
  useKeyFingerprint: vi.fn(),
}));
const { useExportMasterKey, useImportMasterKey, useKeyFingerprint } =
  await import("@/lib/hooks/useSync");
const useExportMock = vi.mocked(useExportMasterKey);
const useImportMock = vi.mocked(useImportMasterKey);
const useFingerprintMock = vi.mocked(useKeyFingerprint);

const exportMutate = vi.fn();
const importMutate = vi.fn();

/** Stub both mutations. `exportResult` is what a successful export returns. */
function stub(
  opts: {
    exportResult?: { material: string };
    exportError?: unknown;
    importError?: unknown;
  } = {},
) {
  exportMutate.mockImplementation((_vars, handlers) => {
    if (opts.exportError) return;
    handlers?.onSuccess?.(opts.exportResult ?? { material: "FERNET-KEY-MATERIAL" });
  });
  importMutate.mockImplementation((_material, handlers) => {
    if (opts.importError) return;
    handlers?.onSuccess?.({ locked_refs: [] });
  });
  useExportMock.mockReturnValue({
    mutate: exportMutate,
    isPending: false,
    error: opts.exportError ?? null,
  } as unknown as ReturnType<typeof useExportMasterKey>);
  useImportMock.mockReturnValue({
    mutate: importMutate,
    isPending: false,
    error: opts.importError ?? null,
  } as unknown as ReturnType<typeof useImportMasterKey>);
  useFingerprintMock.mockReturnValue({
    data: { present: true, fingerprint: "abc123def456" },
  } as unknown as ReturnType<typeof useKeyFingerprint>);
}

/** jsdom has no object-URL support; record what the anchor was handed. */
let createObjectURL: ReturnType<typeof vi.fn>;
let revokeObjectURL: ReturnType<typeof vi.fn>;
let clicked: HTMLAnchorElement[];

beforeEach(() => {
  clicked = [];
  createObjectURL = vi.fn(() => "blob:mock");
  revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked.push(this);
  });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** A File whose text() resolves to `content` (jsdom's File lacks text()). */
function keyFile(content: string, name = "coffer-master.key"): File {
  const file = new File([content], name);
  Object.defineProperty(file, "text", { value: () => Promise.resolve(content) });
  return file;
}

describe("SyncMasterKeyCard", () => {
  test("shows no typed-path field — the browser never needs a host path", () => {
    stub();
    render(<SyncMasterKeyCard />);
    expect(screen.queryByLabelText(/key file path/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("key-fingerprint")).toBeInTheDocument();
  });

  test("export downloads the returned key material as coffer-master.key", async () => {
    stub({ exportResult: { material: "FERNET-KEY-MATERIAL" } });
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /export key/i }));

    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(exportMutate).toHaveBeenCalled();
    expect(clicked[0].download).toBe("coffer-master.key");
    expect(clicked[0].getAttribute("href")).toBe("blob:mock");
    // The Blob carries the material, and the object URL is released again.
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
    // The anchor is transient — it must not be left in the document.
    expect(document.querySelector("a[download]")).toBeNull();
    expect(await screen.findByRole("status")).toHaveTextContent(/coffer-master\.key/);
  });

  test("import reads the picked file's contents and posts the material", async () => {
    stub();
    render(<SyncMasterKeyCard />);

    fireEvent.change(screen.getByLabelText(/import key/i), {
      target: { files: [keyFile("  FERNET-KEY-MATERIAL\n")] },
    });

    // The material is trimmed; no path is ever passed.
    await waitFor(() =>
      expect(importMutate).toHaveBeenCalledWith("FERNET-KEY-MATERIAL", expect.anything()),
    );
    expect(await screen.findByRole("status")).toBeInTheDocument();
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

  test("a server rejection of the key material surfaces as an error", () => {
    stub({ importError: new ApiError("MASTER_KEY_FILE_INVALID", "not a valid Fernet key") });
    render(<SyncMasterKeyCard />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  test("a failed export surfaces an error and downloads nothing", () => {
    stub({ exportError: new ApiError("MASTER_KEY_FILE_INVALID", "no master key to export") });
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /export key/i }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(clicked).toHaveLength(0);
  });
});
