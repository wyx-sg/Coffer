// The shared file-browser pieces (Foundations 0.6.03 viewer toolbar, 0.6.04 file
// tree): the tree's rows, states and menu; the toolbar's path and actions; the
// middle-shortened path.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { FileTree, FileTreePanel, type FileTreeRow } from "@/components/files/FileTree";
import { middlePath } from "@/components/files/middlePath";
import { ViewerToolbar } from "@/components/files/ViewerToolbar";
import "@/i18n";

vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({
    open: vi.fn(() => Promise.resolve()),
    reveal: vi.fn(() => Promise.resolve()),
  }),
}));

describe("middlePath", () => {
  test("a path that fits is left alone", () => {
    expect(middlePath("~/.claude/settings.json")).toBe("~/.claude/settings.json");
  });

  test("a long path keeps its start and its end and drops the middle", () => {
    const long =
      "~/.claude/projects/-Users-xing-WorkEnv-AI-Coffer/memory/feedback-worktree-development.md";
    const short = middlePath(long);
    expect(short.startsWith("~/.claude/")).toBe(true);
    expect(short.endsWith("memory/feedback-worktree-development.md")).toBe(true);
    expect(short).toContain("/…/");
    expect(short.length).toBeLessThan(long.length);
  });
});

const ROWS: FileTreeRow[] = [
  { key: "dir", name: "rules", kind: "folder", depth: 0, open: true },
  { key: "a", name: "style.md", kind: "file", depth: 1, selected: true, dirty: true },
  { key: "b", name: "gone.json", kind: "file", depth: 1, missing: true, note: "not created" },
  {
    key: "c",
    name: "MEMORY.md",
    kind: "file",
    depth: 0,
    locked: true,
    menu: <button>more</button>,
  },
];

describe("FileTree", () => {
  test("rows are tree items: the open file is selected and dotted, a missing one says so", () => {
    render(<FileTree rows={ROWS} label="Files" onActivate={() => {}} />);
    expect(screen.getByRole("tree", { name: "Files" })).toBeInTheDocument();
    expect(screen.getByRole("treeitem", { name: "rules" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("treeitem", { name: /style\.md/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("img", { name: "Unsaved changes" })).toBeInTheDocument();
    expect(screen.getByText("not created")).toBeInTheDocument();
  });

  test("clicking a row reports it", () => {
    const onActivate = vi.fn();
    render(<FileTree rows={ROWS} label="Files" onActivate={onActivate} />);
    fireEvent.click(screen.getByText("style.md"));
    expect(onActivate).toHaveBeenCalledWith(expect.objectContaining({ key: "a" }));
  });

  test("the panel's header strip carries the title and, when read-only, a lock", () => {
    render(
      <FileTreePanel title="Files" locked>
        <p>rows</p>
      </FileTreePanel>,
    );
    expect(screen.getByText("Files")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Read-only" })).toBeInTheDocument();
  });
});

describe("ViewerToolbar", () => {
  test("names the path and offers Preview / Source, Open in editor and Reveal", () => {
    const onChange = vi.fn();
    render(
      <ViewerToolbar
        path="~/.claude/CLAUDE.md"
        absPath="/home/u/.claude/CLAUDE.md"
        reveal
        view={{ value: "preview", onChange }}
      />,
    );
    expect(screen.getByText("~/.claude/CLAUDE.md")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    expect(onChange).toHaveBeenCalledWith("source");
    expect(screen.getByRole("button", { name: "Open in editor" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reveal in Finder" })).toBeInTheDocument();
  });

  test("without an absolute path there are no file actions", () => {
    render(<ViewerToolbar path="~/.claude/agents/" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
