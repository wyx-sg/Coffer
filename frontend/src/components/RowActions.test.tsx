// frontend/src/components/RowActions.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExternalLink } from "lucide-react";

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
});
