// src/components/RowActions.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ExternalLink, Trash2 } from "lucide-react";

import { RowActions } from "./RowActions";

describe("RowActions", () => {
  test("renders the primary action and no menu when there are no items", () => {
    render(<RowActions primary={<button>Import</button>} items={[]} menuAriaLabel="more" />);
    expect(screen.getByRole("button", { name: "Import" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "more" })).not.toBeInTheDocument();
  });

  test("opens the overflow menu and fires the item handler", () => {
    const onClick = vi.fn();
    render(
      <RowActions
        primary={<button>Import</button>}
        items={[{ key: "open", label: "Open in editor", icon: ExternalLink, onClick }]}
        menuAriaLabel="more"
      />,
    );
    // The item is hidden until the "⋯" trigger is clicked.
    expect(screen.queryByText("Open in editor")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "more" }));
    fireEvent.click(screen.getByText("Open in editor"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  test("the overflow is a real menu: menuitems, Escape closes it", async () => {
    render(
      <RowActions
        items={[
          { key: "open", label: "Open in editor", onClick: () => {} },
          { key: "delete", label: "Delete", icon: Trash2, onClick: () => {}, destructive: true },
        ]}
        menuAriaLabel="more"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "more" }));
    const menu = await screen.findByRole("menu");
    expect(screen.getAllByRole("menuitem")).toHaveLength(2);
    // Destructive items keep their own styling.
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveClass("text-destructive");
    fireEvent.keyDown(menu, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });

  test("a click on the trigger does not bubble to a clickable row", () => {
    const onRowClick = vi.fn();
    render(
      <div onClick={onRowClick}>
        <RowActions
          items={[{ key: "open", label: "Open in editor", onClick: () => {} }]}
          menuAriaLabel="more"
        />
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "more" }));
    fireEvent.click(screen.getByText("Open in editor"));
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
