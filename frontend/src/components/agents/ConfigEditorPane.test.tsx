// frontend/src/components/agents/ConfigEditorPane.test.tsx
// The right-hand pane reads by default and edits behind an explicit Edit: no
// textarea until the user asks for one, so a pane opened to LOOK at an agent's
// real configuration cannot be changed by a stray keystroke. The viewer toolbar
// carries the path, Preview / Source (Markdown), Open in editor, Reveal and
// Edit — or, while editing, "Unsaved changes" with Revert and Save; a status
// line under the file names the format, whether the draft parses, and what the
// file is for (boards 2.1.40–2.1.45).
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
    // No Read-only / Editing markers: the toolbar says what you can do.
    expect(screen.queryByText("Read-only")).not.toBeInTheDocument();
  });

  test("the toolbar names the file by its path, home-abbreviated", () => {
    render(<ConfigEditorPane {...baseProps({ filePath: "/Users/u/.claude/settings.json" })} />);
    expect(screen.getByText("~/.claude/settings.json")).toBeInTheDocument();
  });

  test("Edit swaps the preview for a line-numbered textarea with Revert and Save", () => {
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
    // The editing toolbar is the draft's: no Open in editor beside Save.
    expect(screen.queryByRole("button", { name: /open in editor/i })).not.toBeInTheDocument();
  });

  test("an unsaved draft says so in the toolbar", () => {
    render(
      <ConfigEditorPane {...baseProps({ draft: draftStub({ editing: true, dirty: true }) })} />,
    );
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
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

  test("invalid JSON is marked at its line and holds Save back", () => {
    render(
      <ConfigEditorPane
        {...baseProps({
          draft: draftStub({ editing: true, dirty: true, value: '{\n  "a": 1\n  "b": 2\n}' }),
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/line 3, column \d+: not valid json/i);
    expect(screen.getByText(/save is off until it is/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  test("a stale conflict keeps the draft, says Not saved, and offers a reload", () => {
    const discardAndReload = vi.fn(async () => {});
    render(
      <ConfigEditorPane
        {...baseProps({
          draft: draftStub({
            editing: true,
            dirty: true,
            value: '{"mine": true}',
            error: new Error("stale"),
            conflict: true,
            discardAndReload,
          }),
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /settings.json changed on disk since you opened it/i,
    );
    expect(screen.getByText("Not saved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy my edits/i })).toBeInTheDocument();
    // The point of the conflict path: what the user typed is still on screen.
    expect(screen.getByRole("textbox")).toHaveValue('{"mine": true}');
    fireEvent.click(screen.getByRole("button", { name: /discard and reload/i }));
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
    expect(screen.queryByRole("button", { name: /discard and reload/i })).not.toBeInTheDocument();
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
    expect(screen.getByText("settings.json doesn’t exist yet")).toBeInTheDocument();
    expect(screen.getByText(/claude code reads it if it’s there/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /create settings.json/i }));
    expect(startEditing).toHaveBeenCalled();
    expect(setDraft).toHaveBeenCalledWith("{}\n");
  });

  test("the status line names the format, then what the file is for", () => {
    render(
      <ConfigEditorPane
        {...baseProps({
          format: "markdown",
          name: "CLAUDE.md",
          description: "What this file is for.",
        })}
      />,
    );
    expect(screen.getByText("Markdown")).toBeInTheDocument();
    expect(screen.getByText("What this file is for.")).toBeInTheDocument();
  });

  test("renders no description when none is provided", () => {
    render(<ConfigEditorPane {...baseProps()} />);
    expect(screen.queryByText("What this file is for.")).not.toBeInTheDocument();
  });

  test("Markdown opens as a rendered preview with a Preview / Source switch", () => {
    render(
      <ConfigEditorPane
        {...baseProps({ format: "markdown", name: "CLAUDE.md", content: "# Working here\n\nHi." })}
      />,
    );
    expect(screen.getByRole("heading", { name: "Working here" })).toBeInTheDocument();
    const preview = screen.getByRole("button", { name: "Preview" });
    expect(preview).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    expect(document.querySelector(".cm-content")?.textContent).toContain("# Working here");
  });

  test("open, reveal and Edit are on the toolbar, in that order", () => {
    render(<ConfigEditorPane {...baseProps()} />);
    const labels = ["Open in editor", "Reveal in Finder", "Edit"].map((name) =>
      screen.getByRole("button", { name }),
    );
    for (let i = 1; i < labels.length; i++) {
      expect(
        labels[i - 1].compareDocumentPosition(labels[i]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  test("a file with no on-disk path shows only the editor's own control", () => {
    render(<ConfigEditorPane {...baseProps({ filePath: undefined })} />);
    expect(screen.queryByRole("button", { name: /open in editor/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
  });
});
