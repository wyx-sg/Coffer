import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ResponseRulesField } from "./ResponseRulesField";

describe("ResponseRulesField", () => {
  test("a JSON rule needs a pointer and says so", async () => {
    const onChange = vi.fn();
    render(<ResponseRulesField rules={[]} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    expect(screen.getByPlaceholderText("X-Result-Code")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Read" }), { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "JSON field" }));
    expect(screen.getByPlaceholderText("/status/code")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Header or field"), { target: { value: "status" } });
    expect(screen.getByText(/starts with \//)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Header or field"), { target: { value: "/status" } });
    fireEvent.change(screen.getByLabelText("Success values"), { target: { value: "0" } });
    expect(onChange).toHaveBeenLastCalledWith([
      { source: "json", name: "/status", ok_values: ["0"], missing: "ok", message: null },
    ]);
  });

  test("a status rule has no name or If missing, and checks the numbers", () => {
    render(
      <ResponseRulesField
        rules={[{ source: "status", ok_values: ["200", "700"] }]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("Header or field")).toBeNull();
    expect(screen.queryByRole("combobox", { name: "If missing" })).toBeNull();
    expect(screen.getByText(/from 100 to 599/)).toBeInTheDocument();
  });

  test("an error message source adds a name and goes up", async () => {
    const onChange = vi.fn();
    render(
      <ResponseRulesField
        rules={[{ source: "header", name: "x-code", ok_values: ["OK"] }]}
        onChange={onChange}
      />,
    );
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Error message from" }), {
      key: "ArrowDown",
    });
    fireEvent.click(await screen.findByRole("option", { name: "Response header" }));
    fireEvent.change(screen.getByLabelText("Message name"), { target: { value: "x-text" } });
    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ message: { source: "header", name: "x-text" } }),
    ]);
  });

  test("stops at ten rules", () => {
    render(<ResponseRulesField rules={[]} onChange={vi.fn()} />);
    for (let i = 0; i < 10; i++) fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    expect(screen.getByRole("button", { name: "Add rule" })).toBeDisabled();
  });
});
