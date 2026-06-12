// components/chat/Composer.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { Composer } from "./Composer";

describe("Composer", () => {
  test("renders textarea and send button", () => {
    render(<Composer onSend={vi.fn()} />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  test("send button disabled when textarea is empty", () => {
    render(<Composer onSend={vi.fn()} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  test("send button enabled once text is entered", () => {
    render(<Composer onSend={vi.fn()} />);
    const textarea = screen.getByRole("textbox");
    act(() => {
      fireEvent.change(textarea, { target: { value: "Hello" } });
    });
    expect(screen.getByRole("button")).not.toBeDisabled();
  });

  test("calls onSend with trimmed text and clears textarea on button click", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const textarea = screen.getByRole("textbox");
    act(() => {
      fireEvent.change(textarea, { target: { value: "Hello world" } });
    });
    act(() => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(onSend).toHaveBeenCalledWith("Hello world");
    expect(textarea).toHaveValue("");
  });

  test("calls onSend on Enter key press", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const textarea = screen.getByRole("textbox");
    act(() => {
      fireEvent.change(textarea, { target: { value: "Hi there" } });
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    });
    expect(onSend).toHaveBeenCalledWith("Hi there");
  });

  test("does NOT call onSend on Shift+Enter", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const textarea = screen.getByRole("textbox");
    act(() => {
      fireEvent.change(textarea, { target: { value: "Line1" } });
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  test("textarea is disabled while streaming", () => {
    render(<Composer onSend={vi.fn()} disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  test("shows streaming hint when disabled", () => {
    render(<Composer onSend={vi.fn()} disabled />);
    expect(screen.getByText(/Waiting for response/i)).toBeInTheDocument();
  });

  test("shows a Stop button while streaming and calls onStop", () => {
    const onStop = vi.fn();
    render(<Composer onSend={vi.fn()} disabled onStop={onStop} />);
    const stop = screen.getByRole("button", { name: /stop/i });
    act(() => {
      fireEvent.click(stop);
    });
    expect(onStop).toHaveBeenCalled();
  });

  test("no Stop button when not streaming", () => {
    render(<Composer onSend={vi.fn()} onStop={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /stop/i })).not.toBeInTheDocument();
  });
});
