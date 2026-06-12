// frontend/src/components/agents/ConfigFileTree.test.tsx
// Each config entry shows display name + mono path, plus a muted one-line
// description of what the file is FOR — but only for keys we have copy for;
// an unknown key renders no description (never a raw i18n key).
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfigFileTree } from "./ConfigFileTree";
import type { ConfigFileInfo } from "@/lib/api/agents";
import en from "@/i18n/locales/en.json";

function noop() {}

function renderTree(files: ConfigFileInfo[]) {
  return render(
    <ConfigFileTree
      files={files}
      selectedKey={null}
      selectedChild={null}
      expandedDirs={{}}
      onSelectFile={noop}
      onSelectDirectory={noop}
      onSelectChild={vi.fn()}
      onNewFile={noop}
    />,
  );
}

const SETTINGS: ConfigFileInfo = {
  key: "settings",
  display_name: "User settings",
  path: "/home/u/.claude/settings.json",
  format: "json",
  exists: true,
  size: 17,
  modified_at: "2026-05-22T00:00:00Z",
};

describe("ConfigFileTree descriptions", () => {
  test("renders the i18n description line for a known key", () => {
    renderTree([SETTINGS]);
    expect(screen.getByText(en.agents.config.desc.settings)).toBeInTheDocument();
  });

  test("renders a description for a directory-backed known key", () => {
    renderTree([
      {
        key: "subagents",
        display_name: "Subagents (agents/)",
        path: "/home/u/.claude/agents",
        format: "markdown",
        exists: true,
        size: null,
        modified_at: null,
        kind: "directory",
        files: [],
      },
    ]);
    expect(screen.getByText(en.agents.config.desc.subagents)).toBeInTheDocument();
  });

  test("renders no description (and no raw key) for an unknown key", () => {
    renderTree([{ ...SETTINGS, key: "mystery", display_name: "Mystery file" }]);
    expect(screen.getByText("Mystery file")).toBeInTheDocument();
    expect(screen.queryByText(/agents\.config\.desc/)).not.toBeInTheDocument();
  });
});
