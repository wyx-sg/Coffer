// frontend/src/components/agents/ConfigFileTree.test.tsx
// Each config entry shows its display name + mono path. The "what is this file
// for" description was moved to the right-hand editor pane (ConfigEditorPane),
// so the tree itself renders no description copy for any key.
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

describe("ConfigFileTree", () => {
  test("renders the display name and mono path for an entry", () => {
    renderTree([SETTINGS]);
    expect(screen.getByText("User settings")).toBeInTheDocument();
    expect(screen.getByText(SETTINGS.path)).toBeInTheDocument();
  });

  test("does not render the description line in the tree (moved to the pane)", () => {
    renderTree([SETTINGS]);
    expect(
      screen.queryByText(en.agents.config.desc.settings),
    ).not.toBeInTheDocument();
  });
});
