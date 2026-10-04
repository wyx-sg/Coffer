// frontend/src/components/agents/ConfigFileTree.test.tsx
// The config tree is one tree: the config directory as a folder of its files
// (a file beside it at the top level), a directory entry as a folder of its
// own files, a missing file italic with "not created", the open file dotted
// while it has unsaved edits.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ConfigFileTree, type ConfigFileTreeProps } from "./ConfigFileTree";
import type { ConfigFileInfo } from "@/lib/api/agents";
import "@/i18n";

const entry = (over: Partial<ConfigFileInfo>): ConfigFileInfo => ({
  key: "config",
  display_name: "Config (config.toml)",
  path: "/home/u/.codex/config.toml",
  folder_path: "/home/u/.codex",
  kind: "file",
  format: "toml",
  exists: true,
  files: null,
  size: 1,
  modified_at: null,
  ...over,
});

function renderTree(files: ConfigFileInfo[], over: Partial<ConfigFileTreeProps> = {}) {
  const handlers = {
    onSelectFile: vi.fn(),
    onSelectDirectory: vi.fn(),
    onSelectChild: vi.fn(),
  };
  render(
    <ConfigFileTree
      files={files}
      selectedKey={null}
      selectedChild={null}
      collapsed={{}}
      {...handlers}
      {...over}
    />,
  );
  return handlers;
}

describe("ConfigFileTree", () => {
  test("rows are the file's own name under its folder, with no role labels", () => {
    const h = renderTree([
      entry({}),
      entry({ key: "hooks", path: "/home/u/.codex/hooks.json", exists: false }),
    ]);
    expect(screen.getByText("config.toml")).toBeInTheDocument();
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
    expect(screen.getByText("not created")).toBeInTheDocument();
    expect(screen.getByText("~/.codex")).toBeInTheDocument();
    expect(screen.queryByText("~ (home)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("config.toml"));
    expect(h.onSelectFile).toHaveBeenCalledWith("config");
  });

  test("a file kept beside the config directory sits at the top level as ~/name", () => {
    renderTree([entry({ key: "global", path: "/home/u/.claude.json", folder_path: "/home/u" })]);
    expect(screen.getByText("~/.claude.json")).toBeInTheDocument();
  });

  test("a directory entry is a folder of its files; a folded one hides them", () => {
    const dir = entry({
      key: "subagents",
      path: "/home/u/.claude/agents",
      folder_path: "/home/u/.claude",
      kind: "directory",
      files: [{ relpath: "a.md", size: 1, modified_at: "2026-09-01T00:00:00Z" }],
    });
    const h = renderTree([dir]);
    fireEvent.click(screen.getByText("a.md"));
    expect(h.onSelectChild).toHaveBeenCalledWith("subagents", "a.md");
    const row = screen.getByRole("treeitem", { name: "agents" });
    expect(row).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(row);
    expect(h.onSelectDirectory).toHaveBeenCalledWith("subagents");
  });

  test("the config directory folds on its own row", () => {
    renderTree([entry({})]);
    fireEvent.click(screen.getByRole("treeitem", { name: "~/.codex" }));
    expect(screen.queryByText("config.toml")).not.toBeInTheDocument();
  });

  test("an open file with unsaved edits wears the dot", () => {
    renderTree([entry({})], { selectedKey: "config", dirty: true });
    expect(screen.getByRole("img", { name: "Unsaved changes" })).toBeInTheDocument();
  });
});
