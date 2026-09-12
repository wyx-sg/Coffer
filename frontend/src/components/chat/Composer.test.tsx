// components/chat/Composer.test.tsx
import { createRef } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { Composer, type ComposerHandle } from "./Composer";

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

  test("does NOT call onSend on Enter while an IME composition is active", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const textarea = screen.getByRole("textbox");
    act(() => {
      fireEvent.change(textarea, { target: { value: "你好" } });
      // The Enter that commits a pinyin candidate carries isComposing=true.
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false, isComposing: true });
    });
    expect(onSend).not.toHaveBeenCalled();
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

  test("textarea stays ENABLED while a turn streams (the next message queues)", () => {
    render(<Composer onSend={vi.fn()} streaming />);
    expect(screen.getByRole("textbox")).not.toBeDisabled();
  });

  test("can still send while streaming", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} streaming />);
    const textarea = screen.getByRole("textbox");
    act(() => {
      fireEvent.change(textarea, { target: { value: "queue me" } });
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    });
    expect(onSend).toHaveBeenCalledWith("queue me");
  });

  test("shows a 'will queue' hint while streaming", () => {
    render(<Composer onSend={vi.fn()} streaming />);
    expect(screen.getByText(/will queue/i)).toBeInTheDocument();
  });

  test("shows a Stop button while streaming and calls onStop", () => {
    const onStop = vi.fn();
    render(<Composer onSend={vi.fn()} streaming onStop={onStop} />);
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

  test("hard-disabled composer (draft creating) blocks input and send", () => {
    render(<Composer onSend={vi.fn()} disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  test("setText() loads text into the input (used when editing a queued message)", () => {
    const ref = createRef<ComposerHandle>();
    render(<Composer ref={ref} onSend={vi.fn()} />);
    act(() => {
      ref.current?.setText("edited draft");
    });
    expect(screen.getByRole("textbox")).toHaveValue("edited draft");
  });
});
