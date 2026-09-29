// frontend/src/components/agents/ConfigEditorPane.test.tsx
// The right-hand pane reads by default and edits behind an explicit Edit: no
// textarea until the user asks for one, so a pane opened to LOOK at an agent's
// real configuration cannot be changed by a stray keystroke. It also shows the
// path plus an optional one-line description, and renders the FileActions
// (daemon-backed open/reveal) on the same row as Edit / Save / Cancel so the
// user can open the file in their own editor instead.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ConfigEditorPane, type ConfigEditorPaneProps } from "./ConfigEditorPane";

type Draft = ConfigEditorPaneProps["draft"];

function draftStub(overrides: Partial<Draft> = {}): Draft {
  return {
    value: "{}",
    dirty: false,
    editing: false,
    setDraft: vi.fn(),
    startEditing: vi.fn(),
    cancel: vi.fn(),
    save: vi.fn(),
    saving: false,
    error: null,
    conflict: false,
    discardAndReload: vi.fn(async () => {}),
    ...overrides,
  } as Draft;
}

function baseProps(overrides: Partial<ConfigEditorPaneProps> = {}): ConfigEditorPaneProps {
  return {
    pathLabel: "/home/u/.claude/settings.json",
    filePath: "/home/u/.claude/settings.json",
    formatLabel: "json",
    editorKey: "settings",
    content: "{}",
    loading: false,
    draft: draftStub(),
    readOnlyMissing: false,
    ...overrides,
  };
}

describe("ConfigEditorPane", () => {
  test("previews the content until the user asks to edit", () => {
    render(<ConfigEditorPane {...baseProps({ content: '{"theme":"dark"}' })} />);
    // The content shows in a read-only CodeMirror editor (contenteditable=false),
    // never an editable field. Syntax highlighting splits tokens across spans, so
    // assert on the editor's concatenated text.
    const content = document.querySelector(".cm-content");
    expect(content?.textContent).toContain('{"theme":"dark"}');
    expect(content?.getAttribute("contenteditable")).toBe("false");
    expect(document.querySelector("textarea")).toBeNull();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
  });

  test("Edit swaps the preview for a textarea with Save and Cancel", () => {
    const startEditing = vi.fn();
    const { rerender } = render(
      <ConfigEditorPane {...baseProps({ draft: draftStub({ startEditing }) })} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(startEditing).toHaveBeenCalled();

    rerender(<ConfigEditorPane {...baseProps({ draft: draftStub({ editing: true }) })} />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^cancel$/i })).toBeInTheDocument();
  });

  test("Save stays disabled until the draft actually differs", () => {
    render(
      <ConfigEditorPane {...baseProps({ draft: draftStub({ editing: true, dirty: false }) })} />,
    );
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  test("a stale conflict keeps the draft and offers a reload", () => {
    const discardAndReload = vi.fn(async () => {});
    render(
      <ConfigEditorPane
        {...baseProps({
          draft: draftStub({
            editing: true,
            dirty: true,
            value: "my unsaved edit",
            error: new Error("stale"),
            conflict: true,
            discardAndReload,
          }),
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/changed on disk/i);
    // The point of the conflict path: what the user typed is still on screen.
    expect(screen.getByRole("textbox")).toHaveValue("my unsaved edit");
    fireEvent.click(screen.getByRole("button", { name: /discard my edits/i }));
    expect(discardAndReload).toHaveBeenCalled();
  });

  test("a format error is shown against the editor, with no reload offer", () => {
    render(
      <ConfigEditorPane
        {...baseProps({
          draft: draftStub({ editing: true, dirty: true, error: new Error("bad json") }),
        })}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /discard my edits/i })).not.toBeInTheDocument();
  });

  test("a not-yet-created file cannot be edited", () => {
    render(<ConfigEditorPane {...baseProps({ readOnlyMissing: true })} />);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/not created yet/i)).toBeInTheDocument();
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

  test("open, reveal and Edit sit on one row, file actions first", () => {
    render(<ConfigEditorPane {...baseProps()} />);
    const row = screen.getByTestId("file-editor-actions");
    const labels = within(row)
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(labels).toHaveLength(3);
    expect(labels[0]).toMatch(/open in editor/i);
    expect(labels[1]).toMatch(/reveal/i);
    expect(labels[2]).toMatch(/^edit$/i);
  });

  test("while editing, the file actions share the row with Cancel and Save", () => {
    render(<ConfigEditorPane {...baseProps({ draft: draftStub({ editing: true }) })} />);
    const row = screen.getByTestId("file-editor-actions");
    expect(within(row).getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /^cancel$/i })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /^save$/i })).toBeInTheDocument();
  });

  test("a file with no on-disk path shows only the editor's own control", () => {
    render(<ConfigEditorPane {...baseProps({ filePath: undefined })} />);
    const row = screen.getByTestId("file-editor-actions");
    expect(
      within(row)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["Edit"]);
  });
});
