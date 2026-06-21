// frontend/src/components/FileActions.test.tsx
import { beforeEach, describe, expect, test, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { FileActions } from "./FileActions";
import { fsApi } from "@/lib/api/fs";
import { isTauri } from "@/lib/tauri";

vi.mock("@/lib/tauri", () => ({ isTauri: vi.fn() }));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));

// Stand-in for the Tauri opener plugin (only loaded inside the desktop app).
const { openPath, revealItemInDir } = vi.hoisted(() => ({
  openPath: vi.fn(),
  revealItemInDir: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-opener", () => ({ openPath, revealItemInDir }));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  openPath.mockResolvedValue(undefined);
  revealItemInDir.mockResolvedValue(undefined);
  (fsApi.open as Mock).mockResolvedValue(undefined);
  (fsApi.reveal as Mock).mockResolvedValue(undefined);
});

describe("FileActions on the web (daemon-backed)", () => {
  beforeEach(() => (isTauri as Mock).mockReturnValue(false));

  test("opens the file through the daemon (OS default when no editor set)", async () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith("/abs/file.md", undefined));
  });

  test("passes the preferred editor to the daemon", async () => {
    localStorage.setItem("coffer.preferredEditor", "code");
    render(<FileActions filePath="/abs/file.md" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith("/abs/file.md", "code"));
  });

  test("reveals the file through the daemon", async () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith("/abs/file.md"));
  });

  test("opens the containing folder through the daemon", async () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    fireEvent.click(screen.getByRole("button", { name: /open folder/i }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith("/abs", undefined));
  });

  test("no copy-path affordance remains", () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
  });

  test("does not reach for the native Tauri opener on the web", async () => {
    render(<FileActions filePath="/abs/file.md" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalled());
    expect(openPath).not.toHaveBeenCalled();
  });
});

describe("FileActions in the desktop app", () => {
  beforeEach(() => (isTauri as Mock).mockReturnValue(true));

  test("opens the file with the Tauri opener (OS default)", async () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(openPath).toHaveBeenCalledWith("/abs/file.md", undefined));
    expect(fsApi.open).not.toHaveBeenCalled();
  });

  test("opens with the configured preferred editor", async () => {
    localStorage.setItem("coffer.preferredEditor", "code");
    render(<FileActions filePath="/abs/file.md" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(openPath).toHaveBeenCalledWith("/abs/file.md", "code"));
  });

  test("reveals the file with the Tauri opener", async () => {
    render(<FileActions filePath="/abs/file.md" />);
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    await waitFor(() => expect(revealItemInDir).toHaveBeenCalledWith("/abs/file.md"));
  });

  test("falls back to the daemon when the native opener fails", async () => {
    openPath.mockRejectedValue(new Error("plugin missing"));
    render(<FileActions filePath="/abs/file.md" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith("/abs/file.md", undefined));
  });
});
