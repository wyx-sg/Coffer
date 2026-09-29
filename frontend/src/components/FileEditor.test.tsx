// frontend/src/components/FileEditor.test.tsx
// The two guard rails around editing a real on-disk file: a dirty draft is not
// thrown away on one click, and a save that lands is announced. Given a file
// path, the open / reveal actions share the one action row with Edit / Save /
// Cancel.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { FileEditor, type FileEditorProps } from "./FileEditor";
import { ToastProvider } from "@/components/ui/toast";

function baseProps(overrides: Partial<FileEditorProps> = {}): FileEditorProps {
  return {
    value: "hello",
    onChange: vi.fn(),
    editing: true,
    dirty: false,
    saving: false,
    error: null,
    conflict: false,
    onEdit: vi.fn(),
    onCancel: vi.fn(),
    onSave: vi.fn(),
    onDiscardAndReload: vi.fn(),
    ariaLabel: "editor",
    children: <div>rendered</div>,
    ...overrides,
  };
}

describe("FileEditor", () => {
  test("with a file path, open and reveal share the action row with Edit, placed before it", () => {
    render(<FileEditor {...baseProps({ editing: false })} filePath="/home/u/notes.md" />);
    const labels = within(screen.getByTestId("file-editor-actions"))
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(labels).toHaveLength(3);
    expect(labels[0]).toMatch(/open in editor/i);
    expect(labels[1]).toMatch(/reveal/i);
    expect(labels[2]).toMatch(/^edit$/i);
  });

  test("in edit mode the same row carries open and reveal plus Cancel and Save", () => {
    render(<FileEditor {...baseProps()} filePath="/home/u/notes.md" />);
    const labels = within(screen.getByTestId("file-editor-actions"))
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(labels).toHaveLength(4);
    expect(labels[0]).toMatch(/open in editor/i);
    expect(labels[1]).toMatch(/reveal/i);
    expect(labels.slice(2)).toEqual(["Cancel", "Save"]);
  });

  test("without a file path the row holds only the editor's own controls", () => {
    render(<FileEditor {...baseProps({ editing: false })} />);
    expect(
      within(screen.getByTestId("file-editor-actions"))
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["Edit"]);
  });

  test("Cancel on a clean draft leaves edit mode at once", () => {
    const props = baseProps();
    render(<FileEditor {...props} />);
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("Cancel on a dirty draft asks first, and only Discard drops the edits", () => {
    const props = baseProps({ dirty: true });
    render(<FileEditor {...props} />);
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(props.onCancel).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/discard unsaved changes/i);
    fireEvent.click(screen.getByRole("button", { name: /^discard$/i }));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
  });

  test("a save that settles without an error shows a success toast", () => {
    const props = baseProps({ dirty: true });
    const { rerender } = render(
      <ToastProvider>
        <FileEditor {...props} saving />
      </ToastProvider>,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    rerender(
      <ToastProvider>
        <FileEditor {...props} saving={false} editing={false} dirty={false} />
      </ToastProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/saved/i);
  });

  test("a save that fails shows the error, not a success toast", () => {
    const props = baseProps({ dirty: true });
    const { rerender } = render(
      <ToastProvider>
        <FileEditor {...props} saving />
      </ToastProvider>,
    );
    rerender(
      <ToastProvider>
        <FileEditor {...props} saving={false} error={new Error("boom")} />
      </ToastProvider>,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
