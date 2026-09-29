// src/components/ui/menu.test.tsx — the ⋯ action menu: opens, runs an item once, moves by keyboard.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ActionMenu } from "./menu";

function renderMenu(onRemove = vi.fn(), onCopy = vi.fn()) {
  render(
    <ActionMenu
      label="More actions for Codex"
      actions={[
        { key: "copy", label: "Copy uid", onSelect: onCopy },
        { key: "off", label: "Disable", onSelect: vi.fn(), disabled: true },
        {
          key: "rm",
          label: "Remove from Coffer",
          onSelect: onRemove,
          destructive: true,
          separated: true,
        },
      ]}
    />,
  );
  return { onRemove, onCopy };
}

describe("ActionMenu", () => {
  test("opening lists the items as menu items, with a separator before the grouped one", () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Codex" }));
    const menu = screen.getByRole("menu", { name: "More actions for Codex" });
    expect(menu).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Copy uid",
      "Disable",
      "Remove from Coffer",
    ]);
    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Disable" })).toBeDisabled();
  });

  test("choosing an item closes the menu and runs it once", () => {
    const { onRemove } = renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Codex" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove from Coffer" }));
    expect(onRemove).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  test("arrow keys move between the enabled items", () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Codex" }));
    const [copy, , remove] = screen.getAllByRole("menuitem");
    copy.focus();
    fireEvent.keyDown(copy, { key: "ArrowDown" });
    expect(remove).toHaveFocus();
    fireEvent.keyDown(remove, { key: "ArrowDown" });
    expect(copy).toHaveFocus();
    fireEvent.keyDown(copy, { key: "End" });
    expect(remove).toHaveFocus();
  });
});
