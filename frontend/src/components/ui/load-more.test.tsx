// src/components/ui/load-more.test.tsx — the sentinel loads on scroll; the footer says what is loaded and loads by hand.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { LoadMoreFooter, LoadMoreSentinel } from "./load-more";

let observed: { callback: IntersectionObserverCallback }[] = [];
beforeEach(() => {
  observed = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: IntersectionObserverCallback) {
        observed.push({ callback });
      }
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

const intersect = () =>
  act(() =>
    observed
      .at(-1)
      ?.callback(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      ),
  );

test("the sentinel asks for the next page when it scrolls into view, and only while active", () => {
  const onVisible = vi.fn();
  const { rerender } = render(<LoadMoreSentinel active onVisible={onVisible} />);
  intersect();
  expect(onVisible).toHaveBeenCalledTimes(1);
  rerender(<LoadMoreSentinel active={false} onVisible={onVisible} />);
  expect(observed).toHaveLength(1); // no observer set up for an inactive sentinel
});

test("a new page re-arms the sentinel, so a page that left it in view asks again", () => {
  const { rerender } = render(<LoadMoreSentinel active onVisible={() => {}} version={30} />);
  rerender(<LoadMoreSentinel active onVisible={() => {}} version={80} />);
  expect(observed).toHaveLength(2);
});

test("the footer counts what is loaded and loads more by hand", () => {
  const onMore = vi.fn();
  render(<LoadMoreFooter loaded={30} hasMore loading={false} onMore={onMore} />);
  expect(screen.getByText("30 loaded")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(onMore).toHaveBeenCalledTimes(1);
});

test("with a total it reads 'Showing x of y'; at the end there is no button", () => {
  render(
    <LoadMoreFooter loaded={120} total={120} hasMore={false} loading={false} onMore={() => {}} />,
  );
  expect(screen.getByText("Showing 120 of 120")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
