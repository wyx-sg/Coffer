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
