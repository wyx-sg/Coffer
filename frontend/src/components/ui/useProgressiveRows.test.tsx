import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useProgressiveRows } from "./useProgressiveRows";

const rows = Array.from({ length: 12 }, (_, i) => `row-${i}`);

function List({ items, resetKey }: { items: string[]; resetKey?: string }) {
  const { visible, hasMore, sentinel } = useProgressiveRows(items, {
    initial: 5,
    step: 4,
    resetKey,
  });
  return (
    <div>
      <ul>
        {visible.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <span data-testid="more">{String(hasMore)}</span>
      {sentinel}
    </div>
  );
}

let fire: (() => void) | null = null;

beforeEach(() => {
  fire = null;
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: IntersectionObserverCallback) {
        fire = () => cb([{ isIntersecting: true } as IntersectionObserverEntry], this as never);
      }
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("useProgressiveRows", () => {
  it("draws the first slice only", () => {
    render(<List items={rows} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByTestId("more").textContent).toBe("true");
  });

  it("grows by a step each time the sentinel is reached, until every row is drawn", () => {
    render(<List items={rows} />);
    act(() => fire?.());
    expect(screen.getAllByRole("listitem")).toHaveLength(9);
    act(() => fire?.());
    expect(screen.getAllByRole("listitem")).toHaveLength(12);
    expect(screen.getByTestId("more").textContent).toBe("false");
    expect(document.querySelector("[data-load-more-sentinel]")).toBeNull();
  });

  it("starts over when the reset key changes", () => {
    const { rerender } = render(<List items={rows} resetKey="a" />);
    act(() => fire?.());
    expect(screen.getAllByRole("listitem")).toHaveLength(9);
    rerender(<List items={rows} resetKey="b" />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("draws a short list whole with no sentinel", () => {
    render(<List items={rows.slice(0, 3)} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(document.querySelector("[data-load-more-sentinel]")).toBeNull();
  });
});
