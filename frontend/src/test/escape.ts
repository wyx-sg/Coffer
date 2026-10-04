// src/test/escape.ts — press Escape at an open dialog the way a person does.
//
// jsdom counts every focus as keyboard focus (`:focus-visible` always matches),
// so the control a dialog focuses on open shows its tooltip, and an open
// tooltip is the topmost layer: Escape closes it first. In a browser a dialog
// opened with the mouse shows no such tooltip.
import { fireEvent, screen } from "@testing-library/react";

export function pressEscape(target: Element = document.activeElement ?? document.body): void {
  if (screen.queryByRole("tooltip")) {
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  }
  fireEvent.keyDown(target, { key: "Escape" });
}
