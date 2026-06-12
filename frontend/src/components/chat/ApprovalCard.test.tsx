// components/chat/ApprovalCard.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { ApprovalCard } from "./ApprovalCard";

const approval = {
  request_id: "r1",
  tool_use_id: "t1",
  tool_name: "run_command",
  tool_input: { cmd: "ls" },
};

describe("ApprovalCard", () => {
  test("renders the tool name and input", () => {
    render(<ApprovalCard approval={approval} onDecide={vi.fn()} />);
    expect(screen.getByText("run_command")).toBeInTheDocument();
    expect(screen.getByText(/"cmd"/)).toBeInTheDocument();
  });

  test("Allow calls onDecide with 'allow'", () => {
    const onDecide = vi.fn();
    render(<ApprovalCard approval={approval} onDecide={onDecide} />);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /allow/i }));
    });
    expect(onDecide).toHaveBeenCalledWith("allow");
  });

  test("Deny calls onDecide with 'deny'", () => {
    const onDecide = vi.fn();
    render(<ApprovalCard approval={approval} onDecide={onDecide} />);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /deny/i }));
    });
    expect(onDecide).toHaveBeenCalledWith("deny");
  });

  test("buttons are disabled when the disabled prop is set", () => {
    render(<ApprovalCard approval={approval} onDecide={vi.fn()} disabled />);
    expect(screen.getByRole("button", { name: /allow/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /deny/i })).toBeDisabled();
  });
});
