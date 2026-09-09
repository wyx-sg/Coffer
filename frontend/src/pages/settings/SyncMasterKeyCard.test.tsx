// frontend/src/pages/settings/SyncMasterKeyCard.test.tsx
//
// Master-key export/import (spec 010). Clicking a button opens a native dialog
// (mocked here); the chosen path is handed to the mutation. Only when the host
// has no native dialog (pick returns unavailable) does a typed-path field
// appear, after which the buttons act on the typed value.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SyncMasterKeyCard } from "./SyncMasterKeyCard";

vi.mock("@/lib/filePicker", () => ({ pickOpenFile: vi.fn(), pickSaveFile: vi.fn() }));
const { pickOpenFile, pickSaveFile } = await import("@/lib/filePicker");
const pickOpenFileMock = vi.mocked(pickOpenFile);
const pickSaveFileMock = vi.mocked(pickSaveFile);

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

function stub() {
  useExportMock.mockReturnValue({
    mutate: exportMutate,
    isPending: false,
    data: undefined,
  } as unknown as ReturnType<typeof useExportMasterKey>);
  useImportMock.mockReturnValue({
    mutate: importMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useImportMasterKey>);
  useFingerprintMock.mockReturnValue({
    data: { present: true, fingerprint: "abc123def456" },
  } as unknown as ReturnType<typeof useKeyFingerprint>);
}

afterEach(() => vi.clearAllMocks());

describe("SyncMasterKeyCard", () => {
  test("no typed-path field by default", () => {
    stub();
    render(<SyncMasterKeyCard />);
    expect(screen.queryByLabelText(/key file path/i)).not.toBeInTheDocument();
  });

  test("export opens the native save dialog and mutates with the chosen path", async () => {
    stub();
    pickSaveFileMock.mockResolvedValue({ path: "/Users/me/out.key", unavailable: false });
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /export key/i }));

    await waitFor(() => expect(exportMutate).toHaveBeenCalledWith("/Users/me/out.key"));
    expect(pickSaveFileMock).toHaveBeenCalledWith("coffer-master.key");
  });

  test("import opens the native open dialog and mutates with the chosen path", async () => {
    stub();
    pickOpenFileMock.mockResolvedValue({ path: "/Users/me/in.key", unavailable: false });
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /import key/i }));

    await waitFor(() => expect(importMutate).toHaveBeenCalledWith("/Users/me/in.key"));
  });

  test("a cancelled dialog mutates nothing", async () => {
    stub();
    pickSaveFileMock.mockResolvedValue({ path: null, unavailable: false });
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /export key/i }));

    await waitFor(() => expect(pickSaveFileMock).toHaveBeenCalled());
    expect(exportMutate).not.toHaveBeenCalled();
  });

  test("falls back to a typed path when no native dialog is available", async () => {
    stub();
    // First export attempt: no native dialog → reveal the typed field, mutate nothing.
    pickSaveFileMock.mockResolvedValue({ path: null, unavailable: true });
    render(<SyncMasterKeyCard />);

    fireEvent.click(screen.getByRole("button", { name: /export key/i }));

    const input = await screen.findByLabelText(/key file path/i);
    expect(exportMutate).not.toHaveBeenCalled();

    // Now the user types a path and clicks export again — it acts on the typed value
    // without re-opening the (unavailable) dialog.
    fireEvent.change(input, { target: { value: "/typed/coffer.key" } });
    fireEvent.click(screen.getByRole("button", { name: /export key/i }));

    await waitFor(() => expect(exportMutate).toHaveBeenCalledWith("/typed/coffer.key"));
    expect(pickSaveFileMock).toHaveBeenCalledTimes(1);
  });
});
