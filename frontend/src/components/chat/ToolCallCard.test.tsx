// components/chat/ToolCallCard.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ToolCallCard } from "./ToolCallCard";
import type { ContentBlock } from "@/lib/api/chat";
import { contentBlock } from "@/lib/chat/contentBlock";

const makeToolUse = (overrides?: Partial<ContentBlock>): ContentBlock =>
  contentBlock({
    type: "tool_use",
    tool_use_id: "tc-1",
    tool_name: "read_file",
    tool_input: { path: "/etc/hosts" },
    ...overrides,
  });

const makeToolResult = (overrides?: Partial<ContentBlock>): ContentBlock =>
  contentBlock({
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
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  test("shows 'done' status when result provided", () => {
    render(<ToolCallCard toolUse={makeToolUse()} toolResult={makeToolResult()} />);
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  test("shows 'error' status when result has an error", () => {
    render(
      <ToolCallCard
        toolUse={makeToolUse()}
        toolResult={makeToolResult({ output: null, error: "file not found" })}
      />,
    );
    expect(screen.getByText("Error")).toBeInTheDocument();
  });

  test("expands to show input on click", () => {
    render(<ToolCallCard toolUse={makeToolUse()} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getAllByText(/\/etc\/hosts/).length).toBeGreaterThan(1);
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

  test("a done call shows how long it ran", () => {
    render(
      <ToolCallCard toolUse={makeToolUse()} toolResult={makeToolResult({ duration_ms: 300 })} />,
    );
    expect(screen.getByText("Done · 0.3s")).toBeInTheDocument();
  });

  test("a running call is muted text with a spinner, not a status colour", () => {
    const { container } = render(<ToolCallCard toolUse={makeToolUse()} />);
    expect(screen.getByText("Running")).toHaveClass("text-text-muted");
    expect(container.querySelector("[data-spinner]")).not.toBeNull();
  });

  test("a call with no result in a stopped reply reads Stopped, with no spinner", () => {
    const { container } = render(<ToolCallCard toolUse={makeToolUse()} unfinished="stopped" />);
    expect(screen.getByText("Stopped")).toBeInTheDocument();
    expect(container.querySelector("[data-spinner]")).toBeNull();
  });

  test("a call with no result after a lost stream reads Unknown", () => {
    render(<ToolCallCard toolUse={makeToolUse()} unfinished="lost" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
  });
});
