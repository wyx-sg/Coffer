// frontend/src/components/agents/ConfigEditorPane.test.tsx
// The right-hand pane reads by default and edits behind an explicit Edit: no
// textarea until the user asks for one, so a pane opened to LOOK at an agent's
// real configuration cannot be changed by a stray keystroke. It shows the
// file's name and state, an optional one-line description, the FileActions
// (daemon-backed open/reveal) beside Edit / Revert / Save, and a footer with
// the format and the absolute path.
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
    name: "settings.json",
    filePath: "/home/u/.claude/settings.json",
    format: "json",
    content: "{}",
    loading: false,
    draft: draftStub(),
    missing: false,
    agentName: "Claude Code",
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

  test("Edit swaps the preview for a textarea with Revert and Save", () => {
    const startEditing = vi.fn();
    const { rerender } = render(
      <ConfigEditorPane {...baseProps({ draft: draftStub({ startEditing }) })} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(startEditing).toHaveBeenCalled();

    rerender(<ConfigEditorPane {...baseProps({ draft: draftStub({ editing: true }) })} />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^revert$/i })).toBeInTheDocument();
    expect(screen.getByText("Valid JSON")).toBeInTheDocument();
  });

  test("Revert with a dirty draft asks before dropping it", () => {
    const cancel = vi.fn();
    render(
      <ConfigEditorPane
        {...baseProps({ draft: draftStub({ editing: true, dirty: true, value: "{ }", cancel }) })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^revert$/i }));
    expect(cancel).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /discard/i }));
    expect(cancel).toHaveBeenCalled();
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
    expect(screen.getByRole("alert")).toHaveTextContent(
      /save refused — settings.json changed on disk/i,
    );
    expect(screen.getByRole("button", { name: /copy my edits/i })).toBeInTheDocument();
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

  test("a not-yet-created file offers Create instead of Edit", () => {
    const startEditing = vi.fn();
    const setDraft = vi.fn();
    render(
      <ConfigEditorPane
        {...baseProps({ missing: true, draft: draftStub({ startEditing, setDraft }) })}
      />,
    );
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText("Not created")).toBeInTheDocument();
    expect(screen.getByText(/claude code reads it if it’s there/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /create settings.json/i }));
    expect(startEditing).toHaveBeenCalled();
    expect(setDraft).toHaveBeenCalledWith("{}\n");
  });

  test("the footer names the format and the absolute path", () => {
    render(<ConfigEditorPane {...baseProps({ format: "markdown", name: "CLAUDE.md" })} />);
    expect(screen.getByText("Markdown")).toBeInTheDocument();
    expect(screen.getByText(/saving keeps a \.bak/i)).toBeInTheDocument();
    expect(screen.getByText("/home/u/.claude/settings.json")).toBeInTheDocument();
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

  test("while editing, the file actions share the row with Revert and Save", () => {
    render(<ConfigEditorPane {...baseProps({ draft: draftStub({ editing: true }) })} />);
    const row = screen.getByTestId("file-editor-actions");
    expect(within(row).getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /^revert$/i })).toBeInTheDocument();
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
