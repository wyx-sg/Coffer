// frontend/src/components/SearchInput.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchInput } from "./SearchInput";

describe("SearchInput", () => {
  test("calls onChange when the user types", () => {
    const onChange = vi.fn();
    render(<SearchInput value="" onChange={onChange} ariaLabel="Search" />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "hello" } });
    expect(onChange).toHaveBeenCalledWith("hello");
  });

  test("does not render a clear button when the value is empty", () => {
    render(<SearchInput value="" onChange={vi.fn()} ariaLabel="Search" />);
    expect(screen.queryByRole("button", { name: /clear/i })).not.toBeInTheDocument();
  });

  test("renders a clear button when the value is non-empty", () => {
    render(<SearchInput value="hello" onChange={vi.fn()} ariaLabel="Search" />);
    expect(screen.getByRole("button", { name: /clear/i })).toBeInTheDocument();
  });

  test("clicking the clear button calls onChange with empty string", () => {
    const onChange = vi.fn();
    render(<SearchInput value="hello" onChange={onChange} ariaLabel="Search" />);
    fireEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(onChange).toHaveBeenCalledWith("");
  });

  test("renders with the given placeholder", () => {
    render(
      <SearchInput value="" onChange={vi.fn()} ariaLabel="Search" placeholder="Search servers…" />,
    );
    expect(screen.getByPlaceholderText("Search servers…")).toBeInTheDocument();
  });

  test("associates the input with the given id for label linking", () => {
    render(<SearchInput value="" onChange={vi.fn()} id="my-search" ariaLabel="Search" />);
    expect(document.getElementById("my-search")).toBeInTheDocument();
  });

  test("fires onSearch on Enter when the value is non-empty", () => {
    const onSearch = vi.fn();
    render(<SearchInput value="hello" onChange={vi.fn()} onSearch={onSearch} ariaLabel="Search" />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  test("does not fire onSearch on Enter when the value is blank", () => {
    const onSearch = vi.fn();
    render(<SearchInput value="   " onChange={vi.fn()} onSearch={onSearch} ariaLabel="Search" />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSearch).not.toHaveBeenCalled();
  });

  test("does not throw on Enter when onSearch is not provided", () => {
    render(<SearchInput value="hello" onChange={vi.fn()} ariaLabel="Search" />);
    expect(() => fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" })).not.toThrow();
  });
});
