import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { CustomToolsFirstRun } from "./CustomToolsFirstRun";

describe("CustomToolsFirstRun", () => {
  it("opens the flow on the way of the card clicked, with no button of its own", () => {
    const onAdd = vi.fn();
    render(<CustomToolsFirstRun onAdd={onAdd} />);
    expect(screen.queryByRole("button", { name: "Add custom tool" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Import an OpenAPI spec/ }));
    expect(onAdd).toHaveBeenLastCalledWith({ way: "import" });
    fireEvent.click(screen.getByRole("button", { name: /Add one request by hand/ }));
    expect(onAdd).toHaveBeenLastCalledWith({ way: "hand" });
  });
});
