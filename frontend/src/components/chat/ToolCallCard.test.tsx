// components/chat/ToolCallCard.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ToolCallCard } from "./ToolCallCard";
import type { ContentBlock } from "@/lib/api/chat";

const makeToolUse = (overrides?: Partial<ContentBlock>): ContentBlock => ({
  type: "tool_use",
  tool_use_id: "tc-1",
  tool_name: "read_file",
  tool_input: { path: "/etc/hosts" },
  ...overrides,
});

const makeToolResult = (overrides?: Partial<ContentBlock>): ContentBlock => ({
  type: "tool_result",
  tool_use_id: "tc-1",
  output: { content: "127.0.0.1 localhost" },
  error: null,
  ...overrides,
});

describe("ToolCallCard", () => {
  test("renders collapsed with tool name visible", () => {
    render(<ToolCallCard toolUse={makeToolUse()} />);
    expect(screen.getByText("read_file")).toBeInTheDocument();
  });

  test("shows 'running' status when no result", () => {
    render(<ToolCallCard toolUse={makeToolUse()} />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  test("shows 'done' status when result provided", () => {
    render(<ToolCallCard toolUse={makeToolUse()} toolResult={makeToolResult()} />);
    expect(screen.getByText("done")).toBeInTheDocument();
  });

  test("shows 'error' status when result has an error", () => {
    render(
      <ToolCallCard
        toolUse={makeToolUse()}
        toolResult={makeToolResult({ output: null, error: "file not found" })}
      />,
    );
    expect(screen.getByText("error")).toBeInTheDocument();
  });

  test("expands to show input on click", () => {
    render(<ToolCallCard toolUse={makeToolUse()} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getByText(/\/etc\/hosts/)).toBeInTheDocument();
  });

  test("expands to show result on click", () => {
    render(<ToolCallCard toolUse={makeToolUse()} toolResult={makeToolResult()} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByText(/localhost/)).toBeInTheDocument();
  });

  test("collapses again on second click", () => {
    render(<ToolCallCard toolUse={makeToolUse()} toolResult={makeToolResult()} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn); // expand
    expect(screen.getByText("Result")).toBeInTheDocument();
    fireEvent.click(btn); // collapse
    expect(screen.queryByText("Result")).not.toBeInTheDocument();
  });

  test("expands to show error message on click when errored", () => {
    const errMsg = "permission denied";
    render(
      <ToolCallCard
        toolUse={makeToolUse()}
        toolResult={makeToolResult({ output: null, error: errMsg })}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(errMsg)).toBeInTheDocument();
  });
});
