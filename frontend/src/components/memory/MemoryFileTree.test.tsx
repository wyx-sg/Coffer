// frontend/src/kinds/memory/MemoryFileTree.test.tsx
//
// The partition browser's contract is narrow and worth pinning: the tree shows
// the folder as it is, picking a file previews it, and the preview never offers
// a way to write — aggregation owns these bytes, so an Edit button here would
// promise something the next sync would take back. Only the network boundary
// (the hooks) is mocked, per agents/frontend.md §8.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { MemoryFileTree } from "@/components/memory/MemoryFileTree";
import type { MemoryFileContentOut, MemoryFileNode } from "@/lib/api/memoryTypes";

vi.mock("@/lib/hooks/useMemory", () => ({
  usePartitionFiles: vi.fn(),
  usePartitionFileContent: vi.fn(),
}));

const { usePartitionFileContent, usePartitionFiles } = await import("@/lib/hooks/useMemory");
const treeMock = vi.mocked(usePartitionFiles);
const contentMock = vi.mocked(usePartitionFileContent);

const ROOT: MemoryFileNode = {
  name: "coffer",
  path: "",
  abs_path: "/Users/dev/.coffer/memory/coffer",
  folder_abs_path: "/Users/dev/.coffer/memory",
  type: "dir",
  size: null,
  truncated: false,
  children: [
    {
      name: "MEMORY.md",
      path: "MEMORY.md",
      abs_path: "/Users/dev/.coffer/memory/coffer/MEMORY.md",
      folder_abs_path: "/Users/dev/.coffer/memory/coffer",
      type: "file",
      size: 42,
      truncated: false,
      children: null,
    },
  ],
};

function stubTree(root: MemoryFileNode | undefined) {
  treeMock.mockReturnValue({
    data: root,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof usePartitionFiles>);
}

function stubContent(data: Partial<MemoryFileContentOut>) {
  contentMock.mockReturnValue({
    data: {
      path: "MEMORY.md",
      abs_path: "/Users/dev/.coffer/memory/coffer/MEMORY.md",
      folder_abs_path: "/Users/dev/.coffer/memory/coffer",
      content: "",
      truncated: false,
      binary: false,
      size: 0,
      ...data,
    },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof usePartitionFileContent>);
}

describe("MemoryFileTree", () => {
  test("shows the partition's folder and asks for a file before previewing one", () => {
    stubTree(ROOT);
    stubContent({});

    render(<MemoryFileTree name="coffer" />);

    expect(screen.getByRole("button", { name: /coffer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MEMORY\.md/ })).toBeInTheDocument();
    expect(screen.getByText(/select a file to view/i)).toBeInTheDocument();
  });

  test("picking a file renders its markdown and the open/reveal actions", () => {
    stubTree(ROOT);
    stubContent({ content: "# Worktrees\n\nalways develop in one" });

    render(<MemoryFileTree name="coffer" />);
    fireEvent.click(screen.getByRole("button", { name: /MEMORY\.md/ }));

    expect(contentMock).toHaveBeenCalledWith("coffer", "MEMORY.md");
    expect(screen.getByRole("heading", { name: "Worktrees" })).toBeInTheDocument();
    // FileActions offers real open/reveal on both surfaces (daemon-backed on web).
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  });

  test("the preview is read-only — aggregation owns these files", () => {
    stubTree(ROOT);
    stubContent({ content: "body" });

    render(<MemoryFileTree name="coffer" />);
    fireEvent.click(screen.getByRole("button", { name: /MEMORY\.md/ }));

    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  test("a binary file says so instead of rendering bytes", () => {
    stubTree(ROOT);
    stubContent({ binary: true, size: 2048, content: "" });

    render(<MemoryFileTree name="coffer" />);
    fireEvent.click(screen.getByRole("button", { name: /MEMORY\.md/ }));

    expect(screen.getByText(/binary file/i)).toBeInTheDocument();
  });
});
