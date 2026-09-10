// frontend/src/pages/settings/SyncBundleCard.test.tsx
//
// Vault export/import (spec vault-export-import). Clicking a button opens the native directory
// dialog (mocked here); the chosen directory is handed to the mutation, with
// credentials only when the opt-in checkbox is on. Only when the host has no
// native dialog (pick returns unavailable) does a typed-path field appear.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SyncBundleCard } from "./SyncBundleCard";

vi.mock("@/lib/filePicker", () => ({ pickDirectory: vi.fn() }));
const { pickDirectory } = await import("@/lib/filePicker");
const pickDirectoryMock = vi.mocked(pickDirectory);

vi.mock("@/lib/hooks/useSync", () => ({
  useExportVault: vi.fn(),
  useImportVault: vi.fn(),
}));
const { useExportVault, useImportVault } = await import("@/lib/hooks/useSync");

const exportMutate = vi.fn();
const importMutate = vi.fn();

function stub(over: { exportData?: unknown; importData?: unknown } = {}) {
  vi.mocked(useExportVault).mockReturnValue({
    mutate: exportMutate,
    isPending: false,
    data: over.exportData,
  } as unknown as ReturnType<typeof useExportVault>);
  vi.mocked(useImportVault).mockReturnValue({
    mutate: importMutate,
    isPending: false,
    data: over.importData,
  } as unknown as ReturnType<typeof useImportVault>);
}

afterEach(() => vi.clearAllMocks());

describe("SyncBundleCard", () => {
  test("no typed-path field by default", () => {
    stub();
    render(<SyncBundleCard />);
    expect(screen.queryByLabelText(/bundle directory/i)).not.toBeInTheDocument();
  });

  test("export picks a directory and omits credentials by default", async () => {
    stub();
    pickDirectoryMock.mockResolvedValue({ path: "/Users/me/bundle", unavailable: false });
    render(<SyncBundleCard />);

    fireEvent.click(screen.getByRole("button", { name: /export vault/i }));

    await waitFor(() =>
      expect(exportMutate).toHaveBeenCalledWith({
        path: "/Users/me/bundle",
        withCredentials: false,
      }),
    );
  });

  test("the credentials opt-in rides the export request", async () => {
    stub();
    pickDirectoryMock.mockResolvedValue({ path: "/Users/me/bundle", unavailable: false });
    render(<SyncBundleCard />);

    fireEvent.click(screen.getByRole("switch", { name: /include credentials/i }));
    fireEvent.click(screen.getByRole("button", { name: /export vault/i }));

    await waitFor(() =>
      expect(exportMutate).toHaveBeenCalledWith({
        path: "/Users/me/bundle",
        withCredentials: true,
      }),
    );
  });

  test("import picks a directory and mutates with it", async () => {
    stub();
    pickDirectoryMock.mockResolvedValue({ path: "/Users/me/in", unavailable: false });
    render(<SyncBundleCard />);

    fireEvent.click(screen.getByRole("button", { name: /import vault/i }));

    await waitFor(() => expect(importMutate).toHaveBeenCalledWith("/Users/me/in"));
  });

  test("a cancelled dialog mutates nothing", async () => {
    stub();
    pickDirectoryMock.mockResolvedValue({ path: null, unavailable: false });
    render(<SyncBundleCard />);

    fireEvent.click(screen.getByRole("button", { name: /export vault/i }));

    await waitFor(() => expect(pickDirectoryMock).toHaveBeenCalled());
    expect(exportMutate).not.toHaveBeenCalled();
  });

  test("falls back to a typed path when no native dialog is available", async () => {
    stub();
    pickDirectoryMock.mockResolvedValue({ path: null, unavailable: true });
    render(<SyncBundleCard />);

    fireEvent.click(screen.getByRole("button", { name: /export vault/i }));

    const input = await screen.findByLabelText(/bundle directory/i);
    expect(exportMutate).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: "/typed/bundle" } });
    fireEvent.click(screen.getByRole("button", { name: /export vault/i }));

    await waitFor(() =>
      expect(exportMutate).toHaveBeenCalledWith({ path: "/typed/bundle", withCredentials: false }),
    );
    expect(pickDirectoryMock).toHaveBeenCalledTimes(1);
  });

  test("renders the export summary: path, per-area counts, and failures", () => {
    stub({
      exportData: {
        path: "/Users/me/bundle",
        counts: { knowledge: 3, resources: 5, credentials: 0 },
        failures: [{ ref: "agent:cursor", reason: "config_dir missing" }],
      },
    });
    render(<SyncBundleCard />);

    const summary = screen.getByTestId("bundle-summary");
    expect(summary).toHaveTextContent("/Users/me/bundle");
    expect(summary).toHaveTextContent("3");
    expect(summary).toHaveTextContent("5");
    // Zero-count areas are dropped rather than shown as noise.
    expect(summary).not.toHaveTextContent(/credentials/i);
    expect(summary).toHaveTextContent("agent:cursor");
    expect(summary).toHaveTextContent("config_dir missing");
  });

  test("renders the import summary", () => {
    stub({ importData: { path: "/Users/me/in", counts: { resources: 2 }, failures: [] } });
    render(<SyncBundleCard />);
    expect(screen.getByTestId("bundle-summary")).toHaveTextContent("/Users/me/in");
  });
});
