import { render, screen } from "@testing-library/react";
import { user as userEvent } from "./testUser";
import { describe, expect, it, vi } from "vitest";

import "@/i18n";
import { FilterRow } from "./FilterRow";

describe("FilterRow", () => {
  it("puts the segmented control first, then search, and hides Clear filters when idle", () => {
    render(
      <FilterRow
        segmented={<div data-testid="seg" />}
        search={{ value: "", onChange: () => {}, placeholder: "Find" }}
        active={false}
        onClear={() => {}}
      >
        <button>pill</button>
      </FilterRow>,
    );
    const seg = screen.getByTestId("seg");
    const search = screen.getByPlaceholderText("Find");
    expect(seg.compareDocumentPosition(search) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();
  });

  it("shows Clear filters while active and calls onClear", async () => {
    const onClear = vi.fn();
    render(<FilterRow active onClear={onClear} />);
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClear).toHaveBeenCalled();
  });
});
