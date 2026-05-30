// frontend/src/components/agents/FolderPicker.test.tsx
//
// In the browser (jsdom — not Tauri), the picker opens a daemon-backed folder
// browser that navigates real directories and returns an absolute path. We
// mock fsApi.browse to serve a small tree.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { FolderPicker } from "./FolderPicker";

vi.mock("@/lib/api/fs", () => ({ fsApi: { browse: vi.fn() } }));
const { fsApi } = await import("@/lib/api/fs");
const browseMock = vi.mocked(fsApi.browse);

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
  test("Browse opens the folder browser and navigating then selecting returns a path", async () => {
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
