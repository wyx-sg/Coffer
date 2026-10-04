// The shared file text editor: ⌘S saves only a changed, unconflicted draft,
// Escape discards, and a conflict puts the banner over the text.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import "@/i18n";
import { FileTextEditor } from "@/components/files/FileTextEditor";

function setup(props: Partial<React.ComponentProps<typeof FileTextEditor>> = {}) {
  const onSave = vi.fn();
  const onDiscard = vi.fn();
  const onChange = vi.fn();
  render(
    <FileTextEditor
      value="hello"
      onChange={onChange}
      ariaLabel="Edit note"
      dirty
      onSave={onSave}
      onDiscard={onDiscard}
      {...props}
    />,
  );
  return { onSave, onDiscard, onChange, box: screen.getByRole("textbox", { name: "Edit note" }) };
}

describe("FileTextEditor", () => {
  test("⌘S saves a changed draft and Escape discards", () => {
    const { box, onSave, onDiscard } = setup();
    fireEvent.keyDown(box, { key: "s", metaKey: true });
    expect(onSave).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(box, { key: "Escape" });
    expect(onDiscard).toHaveBeenCalledTimes(1);
  });

  test("⌘S does nothing while unchanged, saving or in conflict", () => {
    for (const props of [{ dirty: false }, { saving: true }, { isConflict: true }]) {
      const { box, onSave } = setup(props);
      fireEvent.keyDown(box, { key: "s", ctrlKey: true });
      expect(onSave).not.toHaveBeenCalled();
      document.body.innerHTML = "";
    }
  });

  test("typing reports the new text", () => {
    const { box, onChange } = setup();
    fireEvent.change(box, { target: { value: "hello!" } });
    expect(onChange).toHaveBeenCalledWith("hello!");
  });

  test("a conflict shows the banner, a header and the caller's footer", () => {
    setup({
      isConflict: true,
      conflict: {
        title: "Changed on disk",
        text: "Not saved.",
        onCompare: vi.fn(),
        onCopyMine: vi.fn(),
        onReload: vi.fn(),
      },
      header: <p>frontmatter</p>,
      children: <p>footer line</p>,
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Changed on disk");
    expect(screen.getByText("frontmatter")).toBeInTheDocument();
    expect(screen.getByText("footer line")).toBeInTheDocument();
  });
});
