// src/components/agents/tabs/AgentKindTab.test.tsx — the shared list-tab layout: owner filter in the URL, search, empty and error states.
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Puzzle } from "lucide-react";

import "@/i18n";
import type { Owner } from "@/lib/agents/owner";
import { AgentKindTab } from "./AgentKindTab";

interface Row {
  name: string;
  owner: Owner;
}

const ROWS: Row[] = [
  { name: "coffer-guide", owner: "coffer" },
  { name: "release-notes", owner: "own" },
  { name: "lint-fix", owner: "own" },
];

function Where() {
  const { search } = useLocation();
  return <output data-testid="search">{search}</output>;
}

function renderTab(rows: Row[] = ROWS, path = "/agents/codex/skills", extra = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AgentKindTab
        rows={rows}
        summary="3 skills"
        searchPlaceholder="Search skills"
        searchText={(r) => r.name}
        empty={{ icon: Puzzle, title: "Codex has no skills", description: "Skills show up here." }}
        {...extra}
      >
        {(visible) => (
          <ul>
            {visible.map((r) => (
              <li key={r.name}>{r.name}</li>
            ))}
          </ul>
        )}
      </AgentKindTab>
      <Where />
    </MemoryRouter>,
  );
}

const names = () => screen.queryAllByRole("listitem").map((li) => li.textContent);

describe("AgentKindTab", () => {
  // Scenario (revise-web-ui-ia, agent-registry): "the owner filter narrows an installed-kind tab"
  test("the owner filter narrows the rows and is kept in the URL", () => {
    renderTab();
    expect(names()).toEqual(["coffer-guide", "release-notes", "lint-fix"]);
    fireEvent.click(screen.getByRole("radio", { name: "The agent’s own" }));
    expect(names()).toEqual(["release-notes", "lint-fix"]);
    expect(screen.getByTestId("search")).toHaveTextContent("?owner=own");
    fireEvent.click(screen.getByRole("radio", { name: "All" }));
    expect(names()).toHaveLength(3);
    expect(screen.getByTestId("search")).toHaveTextContent("");
  });

  test("a filter in the address is applied on load", () => {
    renderTab(ROWS, "/agents/codex/skills?owner=coffer");
    expect(names()).toEqual(["coffer-guide"]);
    expect(screen.getByRole("radio", { name: "Coffer’s" })).toHaveAttribute("aria-checked", "true");
  });

  test("search narrows within the owner filter", () => {
    renderTab();
    fireEvent.change(screen.getByRole("textbox", { name: "Search skills" }), {
      target: { value: "LINT" },
    });
    expect(names()).toEqual(["lint-fix"]);
  });

  test("an agent with none of the kind gets the shared empty state", () => {
    renderTab([]);
    expect(screen.getByText("Codex has no skills")).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  test("a list that failed to load says so with a retry", () => {
    let retried = 0;
    renderTab([], "/agents/codex/skills", {
      error: new Error("boom"),
      onRetry: () => (retried += 1),
    });
    expect(screen.getByText("Couldn’t read this list")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retried).toBe(1);
  });
});
