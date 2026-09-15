// frontend/src/components/DataTable.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { DataTable, type Column } from "./DataTable";
import { setDefaultPageSize } from "@/lib/preferences";

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
  // The page size is persisted in localStorage; reset it so one test's choice
  // doesn't bleed into the others (which assume the default of 20).
  afterEach(() => localStorage.clear());

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

  test("pagination splits rows into pages", () => {
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        pageSize={2}
        emptyMessage="none"
      />,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.queryByText("gamma")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("gamma")).toBeInTheDocument();
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

  test("isLoading renders skeleton rows capped at 5, never the empty message", () => {
    render(
      <DataTable
        rows={[]}
        columns={COLS}
        rowKey={(r) => r.id}
        pageSize={50}
        isLoading
        emptyMessage="nothing here"
      />,
    );
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(5);
    expect(screen.queryByText("nothing here")).not.toBeInTheDocument();
  });

  test("isLoading follows a smaller page size", () => {
    render(
      <DataTable
        rows={[]}
        columns={COLS}
        rowKey={(r) => r.id}
        pageSize={2}
        isLoading
        emptyMessage="nothing here"
      />,
    );
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(2);
  });

  test("isLoading with rows already present keeps showing the rows", () => {
    render(
      <DataTable rows={ROWS} columns={COLS} rowKey={(r) => r.id} isLoading emptyMessage="none" />,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.queryByTestId("skeleton-row")).not.toBeInTheDocument();
  });

  test("follows the global default page size and updates live when it changes", () => {
    const many: Row[] = Array.from({ length: 12 }, (_, i) => ({
      id: String(i),
      name: `item-${i}`,
    }));
    render(<DataTable rows={many} columns={COLS} rowKey={(r) => r.id} emptyMessage="none" />);
    // Default global size is 20, so all 12 rows show (incl. the last)…
    expect(screen.getByText("item-11")).toBeInTheDocument();

    // …and changing it in Settings to a smaller valid size re-renders the
    // mounted table live: item-11 moves onto page 2.
    act(() => setDefaultPageSize(10));
    expect(screen.getByText("item-0")).toBeInTheDocument();
    expect(screen.queryByText("item-11")).not.toBeInTheDocument();
  });

  test("bulk actions only operate on the currently-filtered rows (selection ∩ filter)", () => {
    let lastSelected: Row[] = [];
    const sel = {
      ariaSelectAll: "all",
      ariaSelectRow: (r: Row) => `row ${r.name}`,
      bulkLabel: (n: number) => `${n} selected`,
      clearLabel: "clear",
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
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(lastSelected.map((r) => r.name)).toEqual(["alpha"]);

    // Clearing the filter must NOT pull the still-hidden rows into the batch,
    // but DOES re-surface selected rows that were filtered out: only "alpha"
    // was ever selected, so the batch stays exactly ["alpha"].
    fireEvent.change(screen.getByRole("textbox", { name: "search" }), { target: { value: "" } });
    expect(lastSelected.map((r) => r.name)).toEqual(["alpha"]);
  });

  test("a row hidden by the filter drops out of the bulk batch", () => {
    let lastSelected: Row[] = [];
    const sel = {
      ariaSelectAll: "all",
      ariaSelectRow: (r: Row) => `row ${r.name}`,
      bulkLabel: (n: number) => `${n} selected`,
      clearLabel: "clear",
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

    // Select alpha + beta while unfiltered, then filter to "beta": alpha is now
    // hidden, so the bulk batch reflects only the visible "beta".
    fireEvent.click(screen.getByRole("checkbox", { name: "row alpha" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "row beta" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "search" }), {
      target: { value: "beta" },
    });
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(lastSelected.map((r) => r.name)).toEqual(["beta"]);
  });

  test("server pagination: renders rows as-is and drives page changes through callbacks", () => {
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();
    // Caller passes ONE page (2 of 50). The table must not slice/hide them and
    // must report 25 pages, delegating next/prev to the callbacks.
    render(
      <DataTable
        rows={ROWS.slice(0, 2)}
        columns={COLS}
        rowKey={(r) => r.id}
        serverPagination={{
          page: 1,
          pageSize: 2,
          total: 50,
          onPageChange,
          onPageSizeChange,
        }}
        emptyMessage="none"
      />,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
    expect(screen.getByText(/page 1 of 25/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  test("controlled search: forwards typing and resets the server page to 1", () => {
    const onChange = vi.fn();
    const onPageChange = vi.fn();
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        search={{ placeholder: "search", value: "", onChange }}
        serverPagination={{
          page: 3,
          pageSize: 10,
          total: 100,
          onPageChange,
          onPageSizeChange: vi.fn(),
        }}
        emptyMessage="none"
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "search" }), { target: { value: "q" } });
    expect(onChange).toHaveBeenCalledWith("q");
    expect(onPageChange).toHaveBeenCalledWith(1);
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
      bulkLabel: (n: number) => `${n} selected`,
      clearLabel: "clear",
      renderBulkActions: () => <span>bulk</span>,
    };
    // pageSize 2 over 3 rows → page 1 holds alpha + beta; gamma is on page 2.
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.id}
        pageSize={2}
        selection={sel}
        emptyMessage="none"
      />,
    );
    // Header checkbox selects only the current page (2 of 3).
    fireEvent.click(screen.getByRole("checkbox", { name: "all" }));
    expect(screen.getByText(/^2 selected$/)).toBeInTheDocument();
    // The escalation banner offers selecting all 3; clicking it selects them all.
    fireEvent.click(screen.getByRole("button", { name: /select all 3/i }));
    expect(screen.getByText(/^3 selected$/)).toBeInTheDocument();
  });
});
