// frontend/src/components/agents/ConfigEditorPane.test.tsx
// The right-hand pane shows the file's path plus an optional one-line
// description (moved here from the left tree). The description renders only
// when provided.
import { createRef } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfigEditorPane, type ConfigEditorPaneProps } from "./ConfigEditorPane";

function baseProps(overrides: Partial<ConfigEditorPaneProps> = {}): ConfigEditorPaneProps {
  return {
    pathLabel: "/home/u/.claude/settings.json",
    formatLabel: "json",
    editorKey: "settings",
    draft: "{}",
    loading: false,
    onDraftChange: vi.fn(),
    textareaRef: createRef<HTMLTextAreaElement>(),
    showFind: false,
    onToggleFind: vi.fn(),
    onDeleteChild: null,
    stale: false,
    onReloadStale: vi.fn(),
    memoryBlock: false,
    saveError: null,
    saved: false,
    savePending: false,
    saveDisabled: true,
    onSave: vi.fn(),
    ...overrides,
  };
}

describe("ConfigEditorPane", () => {
  test("renders the description next to the content when provided", () => {
    render(<ConfigEditorPane {...baseProps({ description: "What this file is for." })} />);
    expect(screen.getByText("What this file is for.")).toBeInTheDocument();
  });

  test("renders no description when none is provided", () => {
    render(<ConfigEditorPane {...baseProps()} />);
    expect(screen.queryByText("What this file is for.")).not.toBeInTheDocument();
  });
});
