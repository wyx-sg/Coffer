// frontend/src/components/FileEditor.test.tsx
// The two guard rails around editing a real on-disk file: a dirty draft is not
// thrown away on one click, and a save that lands is announced.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

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
