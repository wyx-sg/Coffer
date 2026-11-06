import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { CustomToolsFirstRun } from "./CustomToolsFirstRun";
import { NEW_GROUP } from "./addFlow";

describe("CustomToolsFirstRun", () => {
  it("opens the flow on a new group from its card, with no button of its own", () => {
    const onAdd = vi.fn();
    render(<CustomToolsFirstRun onAdd={onAdd} />);
    expect(screen.queryByRole("button", { name: "Add custom tool" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /OpenAPI/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Add one request by hand/ }));
    expect(onAdd).toHaveBeenLastCalledWith({ target: NEW_GROUP, step: "newGroup" });
  });
});
