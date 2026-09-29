// src/components/EmptyState.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { Library } from "lucide-react";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  test("renders the title alone when nothing else is given", () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("renders description and the action slot", () => {
    render(
      <EmptyState
        icon={Library}
        title="No collections yet"
        description="Make one to get started."
        action={<button type="button">New collection</button>}
      />,
    );
    expect(screen.getByText("No collections yet")).toBeInTheDocument();
    expect(screen.getByText("Make one to get started.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New collection" })).toBeInTheDocument();
  });
});

describe("EmptyState tones", () => {
  test("an error tones the tile and keeps both actions", () => {
    const { container } = render(
      <EmptyState
        icon={Library}
        tone="error"
        title="Couldn't load MCP servers"
        action={<button type="button">Retry</button>}
        secondaryAction={<button type="button">Open daemon log</button>}
      />,
    );
    expect(container.querySelector('[data-tone="error"]')).toHaveClass(
      "bg-danger-soft",
      "text-danger",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open daemon log" })).toBeInTheDocument();
  });
});
