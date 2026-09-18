// frontend/src/components/memory/MemoryFileTree.test.tsx
//
// The partition browser's contract is narrow and worth pinning: the tree shows
// the folder as it is — `MEMORY.md`, `notes/`, `RETIRED.md` and `.raw/` —
// picking a file previews it, and the preview never offers a way to write,
// because Coffer's own passes own these bytes and an Edit button here would
// promise something the next pass would take back.
//
// The one asymmetry the tree draws is the one that would mislead if left
// implicit: `.raw/` is the agents' own words, the INPUT the notes were
// distilled from, so it is reachable but marked and closed rather than offered
// as something to read (FR-037). Only the network boundary (the hooks) is
// mocked, per agents/frontend.md §8.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { MemoryFileTree } from "@/components/memory/MemoryFileTree";
import type { MemoryFileContentOut, MemoryFileNode } from "@/lib/api/memoryTypes";
import { isDerivedInput } from "@/lib/memory/derived";

vi.mock("@/lib/hooks/useMemory", () => ({
  usePartitionFiles: vi.fn(),
  usePartitionFileContent: vi.fn(),
}));

const { usePartitionFileContent, usePartitionFiles } = await import("@/lib/hooks/useMemory");
const treeMock = vi.mocked(usePartitionFiles);
const contentMock = vi.mocked(usePartitionFileContent);

const BASE = "/Users/dev/.coffer/memory/coffer";
// The partition's own identity — what `/memory/partitions/{uid}/files…` takes.
// Its folder is still called "coffer", which is why the tree's ROOT node below
// is named that and this constant is not.
const PARTITION_UID = "mp-be27";

function file(name: string, path: string): MemoryFileNode {
  return {
    name,
    path,
    abs_path: `${BASE}/${path}`,
    folder_abs_path: `${BASE}/${path}`.replace(/\/[^/]+$/, ""),
    type: "file",
    // What the daemon sends: `.raw/` and everything under it is input, not
    // Coffer's own writing. The fixture derives it the way the server does
    // rather than hard-coding false, so a `.raw/` file in a test is marked
    // for the same reason it is marked in production.
    derived: isDerivedInput(path),
    size: 42,
    truncated: false,
    children: null,
  };
}

function dir(name: string, path: string, children: MemoryFileNode[]): MemoryFileNode {
  return {
    name,
    path,
    abs_path: `${BASE}/${path}`,
    folder_abs_path: BASE,
    type: "dir",
    derived: isDerivedInput(path),
    size: null,
    truncated: false,
    children,
  };
}

/** A distilled partition as it actually looks on disk (data-model.md). */
const ROOT: MemoryFileNode = {
  name: "coffer",
  path: "",
  abs_path: BASE,
  folder_abs_path: "/Users/dev/.coffer/memory",
  type: "dir",
  size: null,
  derived: false,
  truncated: false,
  children: [
    file("MEMORY.md", "MEMORY.md"),
    dir("notes", "notes", [file("worktree-development.md", "notes/worktree-development.md")]),
    file("RETIRED.md", "RETIRED.md"),
    dir(".raw", ".raw", [file("3f2a91c4de55b071.md", ".raw/3f2a91c4de55b071.md")]),
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
      abs_path: `${BASE}/MEMORY.md`,
      folder_abs_path: BASE,
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

function renderTree() {
  return render(
    <TooltipProvider>
      <MemoryFileTree uid={PARTITION_UID} />
    </TooltipProvider>,
  );
}

describe("MemoryFileTree", () => {
  test("shows the partition's four parts and asks for a file before previewing one", () => {
    stubTree(ROOT);
    stubContent({});

    renderTree();

    expect(screen.getByRole("button", { name: /coffer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MEMORY\.md/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^notes$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /RETIRED\.md/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\.raw/ })).toBeInTheDocument();
    expect(screen.getByText(/select a file to view/i)).toBeInTheDocument();
  });

  test("picking a note renders its markdown and the open/reveal actions", () => {
    stubTree(ROOT);
    stubContent({ content: "# Worktrees\n\nalways develop in one" });

    renderTree();
    fireEvent.click(screen.getByRole("button", { name: /worktree-development\.md/ }));

    expect(contentMock).toHaveBeenCalledWith(PARTITION_UID, "notes/worktree-development.md");
    expect(screen.getByRole("heading", { name: "Worktrees" })).toBeInTheDocument();
    // FileActions offers real open/reveal on both surfaces (daemon-backed on web).
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    // Coffer's own writing carries no caution — only `.raw/` does.
    expect(screen.queryByTestId("memory-derived-notice")).toBeNull();
  });

  test("`.raw/` is marked as derived input and does not open itself", () => {
    stubTree(ROOT);
    stubContent({});

    renderTree();

    expect(screen.getByTestId("memory-derived-badge")).toHaveTextContent(/derived input/i);
    // Closed: the agents' own words must not be the first thing in front of a
    // reader who came for Coffer's notes.
    expect(screen.getByRole("button", { name: /\.raw/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /3f2a91c4de55b071\.md/ })).toBeNull();
  });

  test("a file opened out of `.raw/` says what it is before its content", () => {
    stubTree(ROOT);
    stubContent({ content: "the agent's own words" });

    renderTree();
    fireEvent.click(screen.getByRole("button", { name: /\.raw/ }));
    fireEvent.click(screen.getByRole("button", { name: /3f2a91c4de55b071\.md/ }));

    expect(contentMock).toHaveBeenCalledWith(PARTITION_UID, ".raw/3f2a91c4de55b071.md");
    const notice = screen.getByTestId("memory-derived-notice");
    expect(notice).toHaveTextContent(/derived input/i);
    expect(notice).toHaveTextContent(/not Coffer's own writing/i);
    // Still readable, and still openable in a real editor — marked, not hidden.
    expect(screen.getByText(/the agent's own words/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  });

  test("the preview is read-only — Coffer's own passes own these files", () => {
    stubTree(ROOT);
    stubContent({ content: "body" });

    renderTree();
    fireEvent.click(screen.getByRole("button", { name: /MEMORY\.md/ }));

    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  test("no per-note actions — a partition is a folder, and the surface looks like one", () => {
    // FR-037 states this as a prohibition, so it is asserted as one: nothing
    // here retires, pins or hides an individual note.
    stubTree(ROOT);
    stubContent({ content: "body" });

    renderTree();
    fireEvent.click(screen.getByRole("button", { name: /worktree-development\.md/ }));

    expect(screen.queryByRole("button", { name: /^retire$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^delete$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^hide$/i })).toBeNull();
  });

  test("a binary file says so instead of rendering bytes", () => {
    stubTree(ROOT);
    stubContent({ binary: true, size: 2048, content: "" });

    renderTree();
    fireEvent.click(screen.getByRole("button", { name: /MEMORY\.md/ }));

    expect(screen.getByText(/binary file/i)).toBeInTheDocument();
  });
});
