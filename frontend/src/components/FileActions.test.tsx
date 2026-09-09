// frontend/src/components/FileActions.test.tsx
import { beforeEach, describe, expect, test, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { FileActions } from "./FileActions";
import { fsApi } from "@/lib/api/fs";

vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  (fsApi.open as Mock).mockResolvedValue(undefined);
  (fsApi.reveal as Mock).mockResolvedValue(undefined);
});

describe("FileActions (daemon-backed)", () => {
  test("opens the file through the daemon (OS default when no editor set)", async () => {
    render(<FileActions filePath="/abs/file.md" />);
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
    render(<FileActions filePath="/abs/file.md" />);
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith("/abs/file.md"));
  });

  test("no copy-path affordance remains", () => {
    render(<FileActions filePath="/abs/file.md" />);
    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
  });
});
