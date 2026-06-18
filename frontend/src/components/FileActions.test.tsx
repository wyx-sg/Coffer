// frontend/src/components/FileActions.test.tsx
import { beforeEach, describe, expect, test, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { FileActions } from "./FileActions";
import { isTauri } from "@/lib/tauri";

vi.mock("@/lib/tauri", () => ({ isTauri: vi.fn() }));

// Stand-in for the Tauri opener plugin (only loaded inside the desktop app).
const { openPath, revealItemInDir } = vi.hoisted(() => ({
  openPath: vi.fn(),
  revealItemInDir: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-opener", () => ({ openPath, revealItemInDir }));

const writeText = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  openPath.mockResolvedValue(undefined);
  revealItemInDir.mockResolvedValue(undefined);
  writeText.mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
});

describe("FileActions on the web", () => {
  beforeEach(() => (isTauri as Mock).mockReturnValue(false));

  test("copies the file and folder paths to the clipboard", async () => {
    render(<FileActions filePath="/abs/skills/demo/SKILL.md" folderPath="/abs/skills/demo" />);
    fireEvent.click(screen.getByRole("button", { name: /copy path/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("/abs/skills/demo/SKILL.md"));
    fireEvent.click(screen.getByRole("button", { name: /copy folder path/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("/abs/skills/demo"));
  });

  test("offers no native open/reveal affordances", () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    expect(screen.queryByRole("button", { name: /open in editor/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reveal/i })).toBeNull();
  });
});

describe("FileActions in the desktop app", () => {
  beforeEach(() => (isTauri as Mock).mockReturnValue(true));

  test("opens the file in the OS default app when no editor is configured", async () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(openPath).toHaveBeenCalledWith("/abs/file.md", undefined));
  });

  test("opens with the configured preferred editor", async () => {
    localStorage.setItem("coffer.preferredEditor", "code");
    render(<FileActions filePath="/abs/file.md" />);
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(openPath).toHaveBeenCalledWith("/abs/file.md", "code"));
  });

  test("reveals the file in the OS file manager", async () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    await waitFor(() => expect(revealItemInDir).toHaveBeenCalledWith("/abs/file.md"));
  });

  test("opens the containing folder when one is provided", async () => {
    render(<FileActions filePath="/abs/file.md" folderPath="/abs" />);
    fireEvent.click(screen.getByRole("button", { name: /open folder/i }));
    await waitFor(() => expect(openPath).toHaveBeenCalledWith("/abs", undefined));
  });
});
