// frontend/src/components/agents/ConfigFileTree.test.tsx
// The config tree names each file by its own name and what it is for, groups
// by the directory it lives in, marks a missing file, and folds a directory.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ConfigFileTree } from "./ConfigFileTree";
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

function renderTree(files: ConfigFileInfo[], collapsed: Record<string, boolean> = {}) {
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
      collapsed={collapsed}
      {...handlers}
    />,
  );
  return handlers;
}

describe("ConfigFileTree", () => {
  test("rows are the file's name and role; unknown keys fall back to the listing's name", () => {
    const h = renderTree([
      entry({}),
      entry({ key: "hooks", path: "/home/u/.codex/hooks.json", exists: false }),
      entry({ key: "future", display_name: "Something new", path: "/home/u/.codex/new.md" }),
    ]);
    expect(screen.getByText("config.toml")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("not created")).toBeInTheDocument();
    expect(screen.getByText("Something new")).toBeInTheDocument();
    expect(screen.getByText("~/.codex")).toBeInTheDocument();
    fireEvent.click(screen.getByText("config.toml"));
    expect(h.onSelectFile).toHaveBeenCalledWith("config");
  });

  test("a folded directory hides its files; an open one lists them", () => {
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
    expect(screen.getByRole("button", { name: /agents\// })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  test("a folded directory shows no children", () => {
    renderTree(
      [
        entry({
          key: "subagents",
          path: "/home/u/.claude/agents",
          kind: "directory",
          files: [{ relpath: "a.md", size: 1, modified_at: "2026-09-01T00:00:00Z" }],
        }),
      ],
      { subagents: true },
    );
    expect(screen.queryByText("a.md")).not.toBeInTheDocument();
  });
});
