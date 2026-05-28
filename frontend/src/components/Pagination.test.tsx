// frontend/src/components/Pagination.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Pagination } from "./Pagination";

describe("Pagination", () => {
  test("renders nothing when total is 0", () => {
    const { container } = render(
      <Pagination
        page={1}
        pageCount={0}
        total={0}
        pageSize={20}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  test("prev button is disabled on the first page", () => {
    render(
      <Pagination
        page={1}
        pageCount={5}
        total={100}
        pageSize={20}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /prev/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next/i })).not.toBeDisabled();
  });

  test("next button is disabled on the last page", () => {
    render(
      <Pagination
        page={5}
        pageCount={5}
        total={100}
        pageSize={20}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /prev/i })).not.toBeDisabled();
  });

  test("prev button fires onPageChange with page-1", () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={3}
        pageCount={5}
        total={100}
        pageSize={20}
        onPageChange={onPageChange}
        onPageSizeChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /prev/i }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  test("next button fires onPageChange with page+1", () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={3}
        pageCount={5}
        total={100}
        pageSize={20}
        onPageChange={onPageChange}
        onPageSizeChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(onPageChange).toHaveBeenCalledWith(4);
  });
});
