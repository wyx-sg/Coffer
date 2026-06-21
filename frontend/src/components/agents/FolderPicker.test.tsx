// frontend/src/components/agents/FolderPicker.test.tsx
//
// In the browser (jsdom — not Tauri), Browse first asks the daemon to open the
// OS-native dialog (fsApi.pickFolder); only when no native dialog tool is
// available does it fall back to the in-app daemon-backed folder browser
// (fsApi.browse). We mock both.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { FolderPicker } from "./FolderPicker";

vi.mock("@/lib/api/fs", () => ({ fsApi: { browse: vi.fn(), pickFolder: vi.fn() } }));
const { fsApi } = await import("@/lib/api/fs");
const browseMock = vi.mocked(fsApi.browse);
const pickFolderMock = vi.mocked(fsApi.pickFolder);

const TREE: Record<string, unknown> = {
  "~": { path: "/home/u", parent: "/home", entries: [{ name: ".codex", path: "/home/u/.codex" }] },
  "/home/u/.codex": { path: "/home/u/.codex", parent: "/home/u", entries: [] },
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

afterEach(() => vi.clearAllMocks());

describe("FolderPicker", () => {
  test("uses the daemon native dialog and returns the picked path without opening the browser", async () => {
    pickFolderMock.mockResolvedValue({ available: true, path: "/home/u/picked" });
    const onChange = vi.fn();
    render(<FolderPicker value={null} onChange={onChange} />, { wrapper: wrap(null) });

    fireEvent.click(screen.getByRole("button", { name: /browse/i }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith("/home/u/picked"));
    // Native dialog handled it — the in-app browser never opened.
    expect(browseMock).not.toHaveBeenCalled();
  });

  test("falls back to the in-app folder browser when no native dialog is available", async () => {
    pickFolderMock.mockResolvedValue({ available: false, path: null });
    browseMock.mockImplementation(
      async (path?: string | null) =>
        (TREE[path ?? "~"] ?? TREE["~"]) as Awaited<ReturnType<typeof fsApi.browse>>,
    );
    const onChange = vi.fn();
    render(<FolderPicker value={null} onChange={onChange} />, { wrapper: wrap(null) });

    fireEvent.click(screen.getByRole("button", { name: /browse/i }));

    // The browser lists the home directory's subfolders.
    expect(await screen.findByText(".codex")).toBeInTheDocument();

    // Navigate into .codex, then select it.
    fireEvent.click(screen.getByText(".codex"));
    await waitFor(() => expect(screen.getByText("/home/u/.codex")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /select this folder/i }));

    expect(onChange).toHaveBeenCalledWith("/home/u/.codex");
  });
});
