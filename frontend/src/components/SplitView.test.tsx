// src/components/SplitView.test.tsx — list/detail split: bounds, remembered width, reset, blocked storage.
import "@/test/pointerEvent";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { Profiler } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { blockLocalStorage } from "@/test/blockedStorage";

import { DETAIL_MIN_WIDTH, LIST_MIN_WIDTH, listMaxWidth } from "@/lib/hooks/useResizableWidth";

import { SplitView } from "./SplitView";

let containerWidth = 1400;

beforeEach(() => {
  window.localStorage.clear();
  containerWidth = 1400;
  // jsdom has no layout: give the split (the separator's parent) a width.
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    const w = this.querySelector(":scope > [role=separator]") ? containerWidth : 0;
    return { x: 0, y: 0, top: 0, left: 0, right: w, bottom: 0, width: w, height: 0 } as DOMRect;
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function renderSplit(storageKey = "test.list") {
  return render(
    <SplitView
      storageKey={storageKey}
      defaultListWidth={320}
      label="Resize the list"
      list={<nav>list</nav>}
      detail={<section>detail</section>}
    />,
  );
}

const sep = () => screen.getByRole("separator", { name: "Resize the list" });
const listPane = () => sep().previousElementSibling as HTMLElement;

function drag(from: number, to: number) {
  const el = sep();
  fireEvent.pointerDown(el, { button: 0, pointerId: 1, clientX: from });
  fireEvent.pointerMove(el, { pointerId: 1, clientX: to });
  fireEvent.pointerUp(el, { pointerId: 1, clientX: to });
}

describe("listMaxWidth", () => {
  test("half the split, or what leaves the detail its minimum — whichever is less", () => {
    expect(listMaxWidth(1400)).toBe(700);
    expect(listMaxWidth(800)).toBe(800 - DETAIL_MIN_WIDTH);
  });
});

describe("SplitView", () => {
  test("opens at the default width with the list, divider and detail in a row", () => {
    renderSplit();
    expect(listPane()).toHaveStyle({ width: "320px" });
    expect(screen.getByText("list")).toBeInTheDocument();
    expect(screen.getByText("detail")).toBeInTheDocument();
    expect(sep()).toHaveAttribute("aria-valuemax", "700");
  });

  acceptance("web-ui", "dragging a divider resizes and survives a reload", () => {
    const first = renderSplit();
    drag(320, 420);
    expect(listPane()).toHaveStyle({ width: "420px" });
    first.unmount();

    const again = renderSplit();
    expect(listPane()).toHaveStyle({ width: "420px" });
    again.unmount();

    renderSplit("another.page");
    expect(listPane()).toHaveStyle({ width: "320px" });
  });

  acceptance("web-ui", "a divider cannot be dragged past a pane's minimum", () => {
    const wide = renderSplit();
    drag(320, 200);
    expect(listPane()).toHaveStyle({ width: `${LIST_MIN_WIDTH}px` });
    drag(240, 2000);
    expect(listPane()).toHaveStyle({ width: "700px" }); // 50% of 1400 comes first
    wide.unmount();
    containerWidth = 900;
    renderSplit("test.narrow");
    drag(320, 2000);
    expect(listPane()).toHaveStyle({ width: "420px" }); // 900 − 480 comes first
  });

  test("re-clamps when the split shrinks, and a too-narrow split keeps the list at 240", () => {
    renderSplit();
    drag(320, 650);
    expect(listPane()).toHaveStyle({ width: "650px" });
    containerWidth = 1000;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(listPane()).toHaveStyle({ width: "500px" });
    containerWidth = 500;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(listPane()).toHaveStyle({ width: "240px" });
    // Wide again: the width the viewer chose comes back.
    containerWidth = 1400;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(listPane()).toHaveStyle({ width: "650px" });
  });

  acceptance("web-ui", "double-clicking a divider restores the default", () => {
    const first = renderSplit();
    drag(320, 500);
    fireEvent.doubleClick(sep());
    expect(listPane()).toHaveStyle({ width: "320px" });
    first.unmount();
    renderSplit();
    expect(listPane()).toHaveStyle({ width: "320px" });
  });

  test("← / → move the list by 16px", () => {
    renderSplit();
    fireEvent.keyDown(sep(), { key: "ArrowRight" });
    expect(listPane()).toHaveStyle({ width: "336px" });
    fireEvent.keyDown(sep(), { key: "ArrowLeft" });
    fireEvent.keyDown(sep(), { key: "ArrowLeft" });
    expect(listPane()).toHaveStyle({ width: "304px" });
  });

  acceptance("web-ui", "no stored width falls back to the default", () => {
    const restore = blockLocalStorage("methods");
    try {
      renderSplit();
      expect(listPane()).toHaveStyle({ width: "320px" });
      drag(320, 400);
      expect(listPane()).toHaveStyle({ width: "400px" });
      fireEvent.doubleClick(sep());
      expect(listPane()).toHaveStyle({ width: "320px" });
    } finally {
      restore();
    }
  });

  test("listHidden drops the list and divider but keeps the detail mounted", () => {
    const { rerender } = renderSplit();
    const detail = screen.getByText("detail");
    rerender(
      <SplitView
        storageKey="test.list"
        label="Resize the list"
        listHidden
        list={<nav>list</nav>}
        detail={<section>detail</section>}
      />,
    );
    expect(screen.queryByRole("separator")).toBeNull();
    expect(screen.queryByText("list")).toBeNull();
    expect(screen.getByText("detail")).toBe(detail);
  });

  test("the divider keeps a 12px gutter on both sides of its line", () => {
    renderSplit();
    expect(sep()).toHaveClass("mx-3", "w-px");
  });

  test("a drag moves the pane width without re-rendering either pane, and commits once", () => {
    let listRenders = 0;
    let detailRenders = 0;
    const onRender = (id: string) => () => {
      if (id === "list") listRenders += 1;
      else detailRenders += 1;
    };
    render(
      <SplitView
        storageKey="test.list"
        defaultListWidth={320}
        label="Resize the list"
        list={
          <Profiler id="list" onRender={onRender("list")}>
            <nav>list</nav>
          </Profiler>
        }
        detail={
          <Profiler id="detail" onRender={onRender("detail")}>
            <textarea aria-label="composer" />
          </Profiler>
        }
      />,
    );
    const composer = screen.getByLabelText("composer");
    const before = { listRenders, detailRenders };
    const el = sep();
    fireEvent.pointerDown(el, { button: 0, pointerId: 1, clientX: 320 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 380 });
    expect(listPane()).toHaveStyle({ width: "380px" });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 420 });
    expect(listPane()).toHaveStyle({ width: "420px" });
    // Nothing was stored or re-rendered while the pointer was down.
    expect(window.localStorage.getItem("coffer.split.test.list")).toBeNull();
    expect({ listRenders, detailRenders }).toEqual(before);
    expect(screen.getByLabelText("composer")).toBe(composer);
    expect(composer).not.toHaveAttribute("style");
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 420 });
    expect(window.localStorage.getItem("coffer.split.test.list")).toBe("420");
    expect(listPane()).toHaveStyle({ width: "420px" });
    expect({ listRenders, detailRenders }).toEqual(before);
  });
});
