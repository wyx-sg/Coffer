// Test-only stand-in for user-event (not a dependency here): the two gestures the filter tests need.
import { act, fireEvent } from "@testing-library/react";

export const user = {
  async click(el: Element) {
    await act(async () => {
      fireEvent.click(el);
    });
  },
  async type(el: Element, text: string) {
    await act(async () => {
      fireEvent.change(el, { target: { value: text } });
    });
  },
};
