import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { InTitleBar, TitleBarSlotContext } from "./titleBarSlot";

describe("InTitleBar", () => {
  test("renders in place when the shell leaves no slot", () => {
    render(
      <div data-testid="page">
        <InTitleBar>
          <a href="/x">Back</a>
        </InTitleBar>
      </div>,
    );
    expect(screen.getByTestId("page")).toContainElement(screen.getByText("Back"));
  });

  test("moves into the title bar's slot when there is one", () => {
    const slot = document.createElement("div");
    document.body.appendChild(slot);
    render(
      <TitleBarSlotContext.Provider value={slot}>
        <div data-testid="page">
          <InTitleBar>
            <a href="/x">Back</a>
          </InTitleBar>
        </div>
      </TitleBarSlotContext.Provider>,
    );
    expect(slot).toContainElement(screen.getByText("Back"));
    expect(screen.getByTestId("page")).not.toContainElement(screen.getByText("Back"));
    slot.remove();
  });
});
