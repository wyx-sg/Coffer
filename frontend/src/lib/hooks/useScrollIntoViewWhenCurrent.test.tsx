// src/lib/hooks/useScrollIntoViewWhenCurrent.test.tsx — the open row scrolls into view.
import { render } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { useScrollIntoViewWhenCurrent } from "./useScrollIntoViewWhenCurrent";

function Row({ current }: { current: boolean }) {
  const ref = useScrollIntoViewWhenCurrent<HTMLLIElement>(current);
  return <li ref={ref}>row</li>;
}

describe("useScrollIntoViewWhenCurrent", () => {
  test("scrolls the row into view when it is current, and only then", () => {
    const original = HTMLElement.prototype.scrollIntoView;
    const scroll = vi.fn();
    HTMLElement.prototype.scrollIntoView = scroll;
    try {
      const { rerender } = render(<Row current={false} />);
      expect(scroll).not.toHaveBeenCalled();
      rerender(<Row current />);
      expect(scroll).toHaveBeenCalledWith({ block: "nearest" });
      expect(scroll).toHaveBeenCalledTimes(1);
    } finally {
      HTMLElement.prototype.scrollIntoView = original;
    }
  });
});
