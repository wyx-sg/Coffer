// frontend/src/components/agents/ConfigEditorPane.test.tsx
// The right-hand pane is READ-ONLY: it previews the file's content (no
// editable textarea, no Save, no find/replace), shows the path plus an
// optional one-line description, and renders the FileActions bar so the user
// can open the file in their own editor (daemon-backed open/reveal on the web,
// Tauri on the desktop).
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfigEditorPane, type ConfigEditorPaneProps } from "./ConfigEditorPane";

function baseProps(overrides: Partial<ConfigEditorPaneProps> = {}): ConfigEditorPaneProps {
  return {
    pathLabel: "/home/u/.claude/settings.json",
    filePath: "/home/u/.claude/settings.json",
    folderPath: "/home/u/.claude",
    formatLabel: "json",
    editorKey: "settings",
    content: "{}",
    loading: false,
    memoryBlock: false,
    ...overrides,
  };
}

describe("ConfigEditorPane", () => {
  test("renders the content read-only (no textarea, Save, or find/replace)", () => {
    render(<ConfigEditorPane {...baseProps({ content: '{"theme":"dark"}' })} />);
    // The content shows, but never in an editable control.
    expect(screen.getByText('{"theme":"dark"}')).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /find ?\/ ?replace/i })).not.toBeInTheDocument();
  });

  test("renders the FileActions bar (daemon-backed open/reveal on the web)", () => {
    render(<ConfigEditorPane {...baseProps()} />);
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  });

  test("renders the description next to the content when provided", () => {
    render(<ConfigEditorPane {...baseProps({ description: "What this file is for." })} />);
    expect(screen.getByText("What this file is for.")).toBeInTheDocument();
  });

  test("renders no description when none is provided", () => {
    render(<ConfigEditorPane {...baseProps()} />);
    expect(screen.queryByText("What this file is for.")).not.toBeInTheDocument();
  });

  test("renders the memory-projection annotation when memoryBlock is set", () => {
    render(<ConfigEditorPane {...baseProps({ memoryBlock: true })} />);
    expect(screen.getByText(/memory-projection block/i)).toBeInTheDocument();
  });
});
