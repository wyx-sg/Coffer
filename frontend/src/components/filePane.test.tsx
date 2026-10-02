// src/components/filePane.test.tsx — the fill-to-bottom pane measures against the page's real scroller.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { scrollContainer, useFillToBottom } from "@/components/filePane";

function rect(top: number, height: number): DOMRect {
  return {
    top,
    bottom: top + height,
    height,
    left: 0,
    right: 0,
    width: 0,
    x: 0,
    y: top,
    toJSON: () => ({}),
  };
}

function Pane() {
  const fill = useFillToBottom();
  return <div data-testid="pane" ref={fill.ref} style={fill.style} />;
}

describe("filePane", () => {
  it("treats the overflow wrapper under <main>, not <main>, as the scroller", () => {
    const { container } = render(
      <main>
        <div style={{ overflowY: "auto" }} data-testid="scroller">
          <div>
            <div data-testid="pane" />
          </div>
        </div>
      </main>,
    );
    const pane = container.querySelector<HTMLElement>("[data-testid=pane]")!;
    expect(scrollContainer(pane)?.dataset.testid).toBe("scroller");
  });

  it("falls back to <main> when no ancestor scrolls", () => {
    const { container } = render(
      <main>
        <div data-testid="pane" />
      </main>,
    );
    const pane = container.querySelector<HTMLElement>("[data-testid=pane]")!;
    expect(scrollContainer(pane)?.tagName).toBe("MAIN");
  });

  it("fills from the pane's top to the page content's bottom padding", () => {
    const original = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () {
      const id = (this as HTMLElement).dataset.testid;
      if (id === "scroller") return rect(50, 700);
      if (id === "content") return rect(50, 700);
      if (id === "pane") return rect(200, 0);
      return original.call(this);
    };
    try {
      const { getByTestId } = render(
        <main>
          <div data-testid="scroller" style={{ overflowY: "auto" }}>
            <div data-testid="content">
              <Wrapper />
            </div>
          </div>
        </main>,
      );
      Object.defineProperty(getByTestId("scroller"), "clientHeight", { value: 700 });
      window.dispatchEvent(new Event("resize"));
      // The pane starts 150px into the scroller and the content ends 500px
      // below it: 700 - 150 - 500 = 50, raised to the 320px floor.
      expect(getByTestId("pane").style.height).toBe("320px");
    } finally {
      Element.prototype.getBoundingClientRect = original;
    }
  });
});

function Wrapper() {
  return <Pane />;
}
