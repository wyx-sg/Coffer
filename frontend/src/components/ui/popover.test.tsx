// src/components/ui/popover.test.tsx — a popover opened from a modal dialog keeps its wheel scrolling.
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./dialog";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

describe("PopoverContent", () => {
  test("wheel and touch moves inside it are not cancelled by the dialog's scroll lock", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Edit</DialogTitle>
          <DialogDescription>Fields</DialogDescription>
          <Popover open>
            <PopoverTrigger>pick</PopoverTrigger>
            <PopoverContent>
              <div data-testid="list">row</div>
            </PopoverContent>
          </Popover>
        </DialogContent>
      </Dialog>,
    );
    const list = screen.getByTestId("list");
    expect(fireEvent.wheel(list, { deltaY: 40 })).toBe(true);
    expect(fireEvent.touchMove(list)).toBe(true);
  });
});
