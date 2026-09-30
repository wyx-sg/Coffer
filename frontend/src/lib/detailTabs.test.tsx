// src/lib/detailTabs.test.tsx — the path addressing of a detail page's tabs.
// revise-web-ui-ia: web-ui "a detail tab lives in the path".
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { detailTabPath, detailTabRedirect, useDetailTab } from "./detailTabs";

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

  it("keeps the search params", () => {
    expect(detailTabPath("/skills/hello", "files", TABS, "overview", "?file=a.md")).toBe(
      "/skills/hello/files?file=a.md",
    );
  });
});

describe("detailTabRedirect", () => {
  it("is null for an address that is already canonical", () => {
    expect(detailTabRedirect("/s/a", undefined, "", TABS, "overview")).toBeNull();
    expect(detailTabRedirect("/s/a", "files", "?file=x", TABS, "overview")).toBeNull();
  });

  it("sends an unknown or default :tab segment to the bare address", () => {
    expect(detailTabRedirect("/s/a", "bogus", "", TABS, "overview")).toBe("/s/a");
    expect(detailTabRedirect("/s/a", "overview", "?file=x", TABS, "overview")).toBe("/s/a?file=x");
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

  it("falls back to the default tab for an unknown segment", async () => {
    renderAt("/skills/hello/bogus");
    expect(screen.getByTestId("tab")).toHaveTextContent("overview");
    await waitFor(() => expect(where.url).toBe("/skills/hello"));
  });

  it("does not redirect while disabled", () => {
    renderAt("/skills/hello/bogus", false);
    expect(where.url).toBe("/skills/hello/bogus");
  });
});
