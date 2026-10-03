// src/components/agents/tabs/AgentKindTab.test.tsx — the shared search-and-list region: search, bordered list, empty box, load error.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import "@/i18n";
import { AgentKindTab } from "./AgentKindTab";

interface Row {
  name: string;
}

const ROWS: Row[] = [{ name: "coffer-guide" }, { name: "release-notes" }, { name: "lint-fix" }];

function renderTab(rows: Row[] = ROWS, extra = {}) {
  return render(
    <AgentKindTab
      rows={rows}
      searchPlaceholder="Search skills"
      searchText={(r) => r.name}
      empty={{ title: "Codex has no skills", description: "Skills Codex installs show up here." }}
      noMatch="No skills match."
      {...extra}
    >
      {(visible) =>
        visible.map((r) => (
          <li key={r.name} data-testid="row">
            {r.name}
          </li>
        ))
      }
    </AgentKindTab>,
  );
}

describe("AgentKindTab", () => {
  test("lists the rows in one bordered list under the search", () => {
    renderTab();
    expect(screen.getAllByTestId("row")).toHaveLength(3);
    expect(screen.getAllByTestId("row")[0].parentElement?.tagName).toBe("UL");
  });

  test("search narrows the rows; a query that matches none says so", () => {
    renderTab();
    fireEvent.change(screen.getByLabelText("Search skills"), { target: { value: "lint" } });
    expect(screen.getAllByTestId("row").map((r) => r.textContent)).toEqual(["lint-fix"]);
    fireEvent.change(screen.getByLabelText("Search skills"), { target: { value: "zzz" } });
    expect(screen.getByText("No skills match.")).toBeInTheDocument();
  });

  test("nothing at all is a bordered box with a title and one line, and keeps the search", () => {
    renderTab([]);
    expect(screen.getByText("Codex has no skills")).toBeInTheDocument();
    expect(screen.getByText("Skills Codex installs show up here.")).toBeInTheDocument();
    expect(screen.getByLabelText("Search skills")).toBeInTheDocument();
  });

  test("a list that failed to load is the shared load-error row with Retry", () => {
    const onRetry = vi.fn();
    renderTab([], { error: new Error("boom"), onRetry });
    expect(screen.getByText("Couldn’t read this list")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  test("the notice and the search aside sit around the list", () => {
    renderTab(ROWS, { notice: <p>Heads up</p>, searchAside: <span>?</span> });
    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText("?")).toBeInTheDocument();
  });
});
