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

  test("shows the empty message when there are no rows", () => {
    render(<DataTable rows={[]} columns={COLS} rowKey={(r) => r.id} emptyMessage="nothing here" />);
    expect(screen.getByText("nothing here")).toBeInTheDocument();
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
    fireEvent.click(screen.getByText("alpha"));
    expect(screen.getByText("detail-for-alpha")).toBeInTheDocument();
    // Clicking again collapses it.
    fireEvent.click(screen.getByText("alpha"));
    expect(screen.queryByText("detail-for-alpha")).not.toBeInTheDocument();
  });
});
