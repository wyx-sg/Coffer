// frontend/src/components/DataTable.test.tsx
import { acceptance } from "@/test/acceptance";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { DataTable, type Column } from "./DataTable";
import { RENDER_BATCH } from "@/lib/hooks/useGrowingList";

interface Row {
  id: string;
  name: string;
}
const ROWS: Row[] = [
  { id: "1", name: "alpha" },
  { id: "2", name: "beta" },
  { id: "3", name: "gamma" },
];
const COLS: Column<Row>[] = [{ key: "name", header: "Name", cell: (r) => r.name }];

describe("DataTable", () => {
  // The sentinel at the end of a long list grows it when it scrolls into view.
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
  const reachEnd = () =>
    act(() =>
      observed
        .at(-1)
        ?.callback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          {} as IntersectionObserver,
        ),
    );
  const named = (n: number): Row[] =>
    Array.from({ length: n }, (_, i) => ({ id: String(i), name: `x-${i}` }));
  const bodyRows = () => screen.getAllByRole("row").length - 1;

  test("renders a row per item", () => {
    render(<DataTable rows={ROWS} columns={COLS} rowKey={(r) => r.id} emptyMessage="none" />);
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("gamma")).toBeInTheDocument();
  });

  test("the search box filters rows", () => {
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        search={{ accessor: (r) => r.name, placeholder: "search" }}
        emptyMessage="none"
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "search" }), { target: { value: "bet" } });
    expect(screen.getByText("beta")).toBeInTheDocument();
    expect(screen.queryByText("alpha")).not.toBeInTheDocument();
  });

  test("a bounded list shows whole: every row, no footer, no button", () => {
    render(
      <DataTable
        rows={named(RENDER_BATCH)}
        columns={COLS}
        rowKey={(r) => r.id}
        emptyMessage="none"
      />,
    );
    expect(bodyRows()).toBe(RENDER_BATCH);
    expect(screen.queryByText(/^Showing/)).toBeNull();
    expect(screen.queryByRole("button", { name: /load/i })).toBeNull();
    expect(document.querySelector("[data-load-more-sentinel]")).toBeNull();
  });

  test("past 100 rows the first 100 render and the rest grow 100 at a time as the end scrolls into view", () => {
    render(<DataTable rows={named(250)} columns={COLS} rowKey={(r) => r.id} emptyMessage="none" />);
    expect(bodyRows()).toBe(100);
    expect(screen.queryByRole("button", { name: /load/i })).toBeNull();
    reachEnd();
    expect(bodyRows()).toBe(200);
    reachEnd();
    expect(bodyRows()).toBe(250);
    expect(document.querySelector("[data-load-more-sentinel]")).toBeNull();
  });

  test("a new search starts a long list over at its first 100 rows", () => {
    render(
      <DataTable
        rows={named(250)}
        columns={COLS}
        rowKey={(r) => r.id}
        search={{ accessor: (r) => r.name, placeholder: "search" }}
        emptyMessage="none"
      />,
    );
    reachEnd();
    expect(bodyRows()).toBe(200);
    fireEvent.change(screen.getByRole("textbox", { name: "search" }), { target: { value: "x-" } });
    expect(bodyRows()).toBe(100);
  });

  test("clicking a row fires onRowClick", () => {
    const onRowClick = vi.fn();
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        onRowClick={onRowClick}
        emptyMessage="none"
      />,
    );
    fireEvent.click(screen.getByText("beta"));
    expect(onRowClick).toHaveBeenCalledWith(ROWS[1]);
  });

  test("a clickable row is keyboard-operable: focusable, Enter/Space fire onRowClick", () => {
    const onRowClick = vi.fn();
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        onRowClick={onRowClick}
        emptyMessage="none"
      />,
    );
    const row = screen.getByText("beta").closest("tr")!;
    expect(row).toHaveAttribute("tabindex", "0");
    expect(row.className).toContain("focus-visible:ring-2");
    fireEvent.keyDown(row, { key: "Enter" });
    fireEvent.keyDown(row, { key: " " });
    fireEvent.keyDown(row, { key: "a" });
    expect(onRowClick).toHaveBeenCalledTimes(2);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[1]);
  });

  test("rows without an action are not focusable", () => {
    render(<DataTable rows={ROWS} columns={COLS} rowKey={(r) => r.id} emptyMessage="none" />);
    expect(screen.getByText("beta").closest("tr")).not.toHaveAttribute("tabindex");
  });

  test("a key pressed on an interactive child does not trigger the row action", () => {
    const onRowClick = vi.fn();
    const cols: Column<Row>[] = [
      { key: "name", header: "Name", cell: (r) => <button type="button">act-{r.name}</button> },
    ];
    render(
      <DataTable
        rows={ROWS}
        columns={cols}
        rowKey={(r) => r.id}
        onRowClick={onRowClick}
        emptyMessage="none"
      />,
    );
    fireEvent.keyDown(screen.getByText("act-alpha"), { key: "Enter" });
    expect(onRowClick).not.toHaveBeenCalled();
  });

  test("shows the empty message when there are no rows", () => {
    render(<DataTable rows={[]} columns={COLS} rowKey={(r) => r.id} emptyMessage="nothing here" />);
    expect(screen.getByText("nothing here")).toBeInTheDocument();
  });

  test("renders the optional empty action under the message", () => {
    render(
      <DataTable
        rows={[]}
        columns={COLS}
        rowKey={(r) => r.id}
        emptyMessage="nothing here"
        emptyAction={<button type="button">create one</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "create one" })).toBeInTheDocument();
  });

  test("isLoading renders a few skeleton rows, never the empty message", () => {
    render(
      <DataTable
        rows={[]}
        columns={COLS}
        rowKey={(r) => r.id}
        isLoading
        emptyMessage="nothing here"
      />,
    );
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(5);
    expect(screen.queryByText("nothing here")).not.toBeInTheDocument();
  });

  test("isLoading with rows already present keeps showing the rows", () => {
    render(
      <DataTable rows={ROWS} columns={COLS} rowKey={(r) => r.id} isLoading emptyMessage="none" />,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.queryByTestId("skeleton-row")).not.toBeInTheDocument();
  });

  test("bulk actions only operate on the currently-filtered rows (selection ∩ filter)", () => {
    let lastSelected: Row[] = [];
    const sel = {
      ariaSelectAll: "all",
      ariaSelectRow: (r: Row) => `row ${r.name}`,
      renderBulkActions: ({ selectedRows }: { selectedRows: Row[]; clear: () => void }) => {
        lastSelected = selectedRows;
        return <span>bulk-{selectedRows.length}</span>;
      },
    };
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        search={{ accessor: (r) => r.name, placeholder: "search" }}
        selection={sel}
        emptyMessage="none"
      />,
    );

    // Filter to just "alpha", then select-all → bulk must see only alpha.
    fireEvent.change(screen.getByRole("textbox", { name: "search" }), {
      target: { value: "alpha" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "all" }));
    expect(screen.getByText("1 of 1 selected")).toBeInTheDocument();
    expect(lastSelected.map((r) => r.name)).toEqual(["alpha"]);

    // The bar takes the search box's place; Clear brings the box back with its text.
    expect(screen.queryByRole("textbox", { name: "search" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByRole("textbox", { name: "search" })).toHaveValue("alpha");
  });

  test("a row that leaves the table drops out of the bulk batch", () => {
    let lastSelected: Row[] = [];
    const sel = {
      ariaSelectAll: "all",
      ariaSelectRow: (r: Row) => `row ${r.name}`,
      renderBulkActions: ({ selectedRows }: { selectedRows: Row[]; clear: () => void }) => {
        lastSelected = selectedRows;
        return <span>bulk-{selectedRows.length}</span>;
      },
    };
    const table = (rows: Row[]) => (
      <DataTable
        rows={rows}
        columns={COLS}
        rowKey={(r) => r.id}
        selection={sel}
        emptyMessage="none"
      />
    );
    const { rerender } = render(table(ROWS));
    fireEvent.click(screen.getByRole("checkbox", { name: "row alpha" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "row beta" }));
    expect(screen.getByText("2 of 3 selected")).toBeInTheDocument();

    rerender(table(ROWS.filter((r) => r.name !== "alpha")));
    expect(screen.getByText("1 of 2 selected")).toBeInTheDocument();
    expect(lastSelected.map((r) => r.name)).toEqual(["beta"]);
  });

  acceptance("web-ui", "a selection bar counts the rows and Esc clears it", () => {
    const sel = {
      ariaSelectAll: "all",
      ariaSelectRow: (r: Row) => `row ${r.name}`,
      renderBulkActions: () => <span>bulk</span>,
    };
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        selection={sel}
        emptyMessage="none"
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "row alpha" }));
    expect(screen.getByText("bulk")).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByText("bulk")).toBeNull();
  });

  test("a sortable column sorts newest first, then oldest first, then back to the default order", () => {
    type Run = { id: string; at: string | null };
    const runs: Run[] = [
      { id: "mid", at: "2026-10-02T00:00:00Z" },
      { id: "none", at: null },
      { id: "new", at: "2026-10-03T00:00:00Z" },
      { id: "old", at: "2026-10-01T00:00:00Z" },
    ];
    const cols: Column<Run>[] = [
      { key: "id", header: "Name", cell: (r) => r.id },
      { key: "at", header: "Last used", cell: () => "", sortable: true, sortValue: (r) => r.at },
    ];
    render(<DataTable rows={runs} columns={cols} rowKey={(r) => r.id} emptyMessage="none" />);
    const order = () =>
      screen
        .getAllByRole("row")
        .slice(1)
        .map((r) => r.textContent);
    expect(screen.queryByRole("button", { name: "Name" })).toBeNull();
    const head = screen.getByRole("button", { name: "Last used" });
    expect(order()).toEqual(["mid", "none", "new", "old"]);
    fireEvent.click(head);
    expect(order()).toEqual(["new", "mid", "old", "none"]);
    expect(head.closest("th")).toHaveAttribute("aria-sort", "descending");
    fireEvent.click(head);
    expect(order()).toEqual(["old", "mid", "new", "none"]);
    expect(head.closest("th")).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(head);
    expect(order()).toEqual(["mid", "none", "new", "old"]);
    expect(head.closest("th")).toHaveAttribute("aria-sort", "none");
  });

  test("clicking an expandable row reveals + hides its detail", () => {
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        getRowDetail={(r) => <div>detail-for-{r.name}</div>}
        emptyMessage="none"
      />,
    );
    // Detail is hidden until the row is clicked.
    expect(screen.queryByText("detail-for-alpha")).not.toBeInTheDocument();
    const row = screen.getByText("alpha").closest("tr")!;
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByText("alpha"));
    expect(screen.getByText("detail-for-alpha")).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-expanded", "true");
    // Clicking again collapses it.
    fireEvent.click(screen.getByText("alpha"));
    expect(screen.queryByText("detail-for-alpha")).not.toBeInTheDocument();
    // The keyboard does the same.
    fireEvent.keyDown(row, { key: "Enter" });
    expect(screen.getByText("detail-for-alpha")).toBeInTheDocument();
  });

  test("header checkbox selects the current page; banner escalates to select-all", () => {
    const sel = {
      ariaSelectAll: "all",
      ariaSelectRow: (r: Row) => `row ${r.name}`,
      renderBulkActions: () => <span>bulk</span>,
    };
    // 150 rows: the first 100 render, the other 50 are beyond them.
    render(
      <DataTable
        rows={named(150)}
        columns={COLS}
        rowKey={(r) => r.id}
        selection={sel}
        emptyMessage="none"
      />,
    );
    // Header checkbox selects only the rows rendered (100 of 150).
    fireEvent.click(screen.getByRole("checkbox", { name: "all" }));
    expect(screen.getByText("100 of 150 selected")).toBeInTheDocument();
    // The escalation banner offers selecting all 150; clicking it selects them all.
    fireEvent.click(screen.getByRole("button", { name: /select all 150/i }));
    expect(screen.getByText("150 of 150 selected")).toBeInTheDocument();
  });
  test("rowFooter renders a full-width row under a row, and isRowClickable gates the click", () => {
    const onRowClick = vi.fn();
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        onRowClick={onRowClick}
        isRowClickable={(r) => r.id !== "2"}
        rowFooter={(r) => (r.id === "2" ? <span>notice-for-beta</span> : null)}
        emptyMessage="none"
      />,
    );
    const footer = screen.getByText("notice-for-beta").closest("td");
    expect(footer).toHaveAttribute("colspan", "1");
    // One footer row only: alpha and gamma return null.
    expect(document.querySelectorAll("[data-row-footer]")).toHaveLength(1);
    fireEvent.click(screen.getByText("beta"));
    expect(onRowClick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("alpha"));
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
  });
});
