import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DataCardGrid } from "./DataCardGrid";

interface Row {
  id: string;
  name: string;
}
const ROWS: Row[] = [
  { id: "1", name: "alpha" },
  { id: "2", name: "beta" },
  { id: "3", name: "gamma" },
];

function renderCard(row: Row) {
  return (
    <div data-testid={`card-${row.id}`}>
      <span>{row.name}</span>
    </div>
  );
}

describe("DataCardGrid", () => {
  // The page size is persisted in localStorage; reset between tests.
  afterEach(() => localStorage.clear());

  test("renders a card per item", () => {
    render(
      <DataCardGrid rows={ROWS} rowKey={(r) => r.id} renderCard={renderCard} emptyMessage="none" />,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("gamma")).toBeInTheDocument();
  });

  test("the search box filters cards", () => {
    render(
      <DataCardGrid
        rows={ROWS}
        rowKey={(r) => r.id}
        renderCard={renderCard}
        search={{ accessor: (r) => r.name, placeholder: "search" }}
        emptyMessage="none"
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "search" }), { target: { value: "bet" } });
    expect(screen.getByText("beta")).toBeInTheDocument();
    expect(screen.queryByText("alpha")).not.toBeInTheDocument();
  });

  test("pagination splits cards into pages", () => {
    render(
      <DataCardGrid
        rows={ROWS}
        rowKey={(r) => r.id}
        renderCard={renderCard}
        pageSize={2}
        emptyMessage="none"
      />,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.queryByText("gamma")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("gamma")).toBeInTheDocument();
  });

  test("shows the empty message when there are no rows", () => {
    render(
      <DataCardGrid
        rows={[]}
        rowKey={(r) => r.id}
        renderCard={renderCard}
        emptyMessage="nothing here"
      />,
    );
    expect(screen.getByText("nothing here")).toBeInTheDocument();
  });

  test("clicking a card fires onCardClick", () => {
    const onCardClick = vi.fn();
    render(
      <DataCardGrid
        rows={ROWS}
        rowKey={(r) => r.id}
        renderCard={renderCard}
        onCardClick={onCardClick}
        emptyMessage="none"
      />,
    );
    fireEvent.click(screen.getByText("beta"));
    expect(onCardClick).toHaveBeenCalledWith(ROWS[1]);
  });

  test("an inner button click does NOT fire onCardClick", () => {
    const onCardClick = vi.fn();
    const onInner = vi.fn();
    render(
      <DataCardGrid
        rows={ROWS}
        rowKey={(r) => r.id}
        renderCard={(r) => (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onInner();
            }}
          >
            inner-{r.name}
          </button>
        )}
        onCardClick={onCardClick}
        emptyMessage="none"
      />,
    );
    fireEvent.click(screen.getByText("inner-alpha"));
    expect(onInner).toHaveBeenCalledTimes(1);
    expect(onCardClick).not.toHaveBeenCalled();
  });
});
