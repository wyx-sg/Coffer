// src/lib/detailTabs.test.tsx — the path addressing of a detail page's tabs.
// revise-web-ui-ia: web-ui "a detail tab lives in the path" and
// "an old query-tab address redirects to the path".
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import {
  canonicalDetailPath,
  detailTabPath,
  detailTabRedirect,
  resolveByName,
  useDetailTab,
} from "./detailTabs";

const TABS = ["overview", "files", "history"] as const;

describe("detailTabPath", () => {
  it("is the bare address for the default tab and a segment for any other", () => {
    expect(detailTabPath("/skills/hello", "overview", TABS, "overview")).toBe("/skills/hello");
    expect(detailTabPath("/skills/hello", "files", TABS, "overview")).toBe("/skills/hello/files");
  });

  it("falls back to the bare address for an unknown or missing tab", () => {
    expect(detailTabPath("/skills/hello", "nope", TABS, "overview")).toBe("/skills/hello");
    expect(detailTabPath("/skills/hello", undefined, TABS, "overview")).toBe("/skills/hello");
  });

  it("keeps every search param except tab", () => {
    expect(detailTabPath("/skills/hello", "files", TABS, "overview", "?tab=x&file=a.md")).toBe(
      "/skills/hello/files?file=a.md",
    );
  });
});

describe("canonicalDetailPath / detailTabRedirect", () => {
  it("a legacy ?tab= wins over the path segment and moves into the path", () => {
    expect(canonicalDetailPath("/s/a", undefined, "?tab=files", TABS, "overview")).toBe(
      "/s/a/files",
    );
    expect(detailTabRedirect("/s/a", "history", "?tab=files", TABS, "overview")).toBe("/s/a/files");
  });

  it("is null for an address that is already canonical", () => {
    expect(detailTabRedirect("/s/a", undefined, "", TABS, "overview")).toBeNull();
    expect(detailTabRedirect("/s/a", "files", "?file=x", TABS, "overview")).toBeNull();
  });

  it("sends an unknown or default :tab segment to the bare address", () => {
    expect(detailTabRedirect("/s/a", "bogus", "", TABS, "overview")).toBe("/s/a");
    expect(detailTabRedirect("/s/a", "overview", "?file=x", TABS, "overview")).toBe("/s/a?file=x");
  });
});

describe("resolveByName", () => {
  const items = [
    { uid: "sk-1", name: "hello" },
    { uid: "sk-2", name: "world" },
  ];
  it("matches by name first", () => {
    expect(resolveByName(items, "hello")).toEqual({ item: items[0], byUid: false });
  });
  it("matches an old uid address and says so", () => {
    expect(resolveByName(items, "sk-2")).toEqual({ item: items[1], byUid: true });
  });
  it("is null for no match, an empty key, or a list not yet loaded", () => {
    expect(resolveByName(items, "nope")).toBeNull();
    expect(resolveByName(items, "")).toBeNull();
    expect(resolveByName(undefined, "hello")).toBeNull();
  });
});

const where = { url: "" };
function Probe() {
  const loc = useLocation();
  where.url = loc.pathname + loc.search;
  return null;
}

function Harness({ enabled = true }: { enabled?: boolean }) {
  const [tab, setTab] = useDetailTab(TABS, "overview", "/skills/hello", { enabled });
  return (
    <div>
      <span data-testid="tab">{tab}</span>
      {TABS.map((t) => (
        <button key={t} onClick={() => setTab(t)}>
          {t}
        </button>
      ))}
    </div>
  );
}

function renderAt(entry: string, enabled = true) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route
          path="/skills/:name/:tab?"
          element={
            <>
              <Harness enabled={enabled} />
              <Probe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("useDetailTab", () => {
  it("reads the tab from the path and switches it by navigating", () => {
    renderAt("/skills/hello/files?file=a.md");
    expect(screen.getByTestId("tab")).toHaveTextContent("files");
    fireEvent.click(screen.getByRole("button", { name: "history" }));
    expect(where.url).toBe("/skills/hello/history?file=a.md");
    expect(screen.getByTestId("tab")).toHaveTextContent("history");
    fireEvent.click(screen.getByRole("button", { name: "overview" }));
    expect(where.url).toBe("/skills/hello?file=a.md");
    expect(screen.getByTestId("tab")).toHaveTextContent("overview");
  });

  it("redirects an old ?tab= address to the path, keeping other params", async () => {
    renderAt("/skills/hello?tab=files&file=a.md");
    expect(screen.getByTestId("tab")).toHaveTextContent("files");
    await waitFor(() => expect(where.url).toBe("/skills/hello/files?file=a.md"));
  });

  it("falls back to the default tab for an unknown segment", async () => {
    renderAt("/skills/hello/bogus");
    expect(screen.getByTestId("tab")).toHaveTextContent("overview");
    await waitFor(() => expect(where.url).toBe("/skills/hello"));
  });

  it("does not redirect while disabled", () => {
    renderAt("/skills/hello?tab=files", false);
    expect(where.url).toBe("/skills/hello?tab=files");
  });
});
