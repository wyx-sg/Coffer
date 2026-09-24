// components/chat/Composer.attachments.test.tsx
// The composer's attachments (spec chat "Attach files from the Chat page
// composer"): picked, dropped and pasted files upload at once, show as chips,
// and hold Send until every upload is done.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import type { ChatAttachment } from "@/lib/api/chat";
import { acceptance } from "@/test/acceptance";
import { Composer } from "./Composer";

vi.mock("@/lib/api/chat", () => ({
  chatApi: { uploadAttachment: vi.fn() },
}));

const { chatApi } = await import("@/lib/api/chat");
const uploadMock = vi.mocked(chatApi.uploadAttachment);

function stored(name: string, mime: string, size: number, id = "a".repeat(32)): ChatAttachment {
  return { id, filename: name, mime, size };
}

function pick(file: File) {
  const input = screen.getByTestId("composer-file-input");
  act(() => {
    fireEvent.change(input, { target: { files: [file] } });
  });
}

const sendButton = () => screen.getByRole("button", { name: /send/i });

describe("Composer attachments", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  acceptance("chat", "attaching a file shows a chip and sends it with the message", async () => {
    const png = new File([new Uint8Array(2048)], "shot.png", { type: "image/png" });
    const uploaded = stored("shot.png", "image/png", 2048);
    uploadMock.mockResolvedValue(uploaded);
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /attach files/i }));
    });
    pick(png);

    const list = screen.getByRole("list", { name: /attached files/i });
    expect(list).toHaveTextContent("shot.png");
    expect(list).toHaveTextContent("2 KB");
    expect(uploadMock).toHaveBeenCalledWith(png, expect.any(AbortSignal));
    await waitFor(() => expect(screen.queryByText(/uploading/i)).not.toBeInTheDocument());

    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "what is this?" } });
    });
    act(() => {
      fireEvent.click(sendButton());
    });
    expect(onSend).toHaveBeenCalledWith("what is this?", [uploaded]);
    expect(screen.queryByRole("list", { name: /attached files/i })).not.toBeInTheDocument();
  });

  acceptance("chat", "send waits for uploads in flight", async () => {
    let finish: (value: ChatAttachment) => void = () => {};
    uploadMock.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<Composer onSend={vi.fn()} />);
    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "hi" } });
    });
    pick(new File(["# notes"], "notes.md", { type: "text/markdown" }));

    expect(screen.getByText(/uploading/i)).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();

    await act(async () => {
      finish(stored("notes.md", "text/markdown", 7));
    });
    expect(screen.queryByText(/uploading/i)).not.toBeInTheDocument();
    expect(sendButton()).not.toBeDisabled();
  });

  acceptance("chat", "a failed upload says why and is not sent", async () => {
    uploadMock.mockRejectedValue(
      new ApiError("ATTACHMENT_TYPE_UNSUPPORTED", "unsupported attachment type"),
    );
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "see clip" } });
    });
    pick(new File([new Uint8Array(8)], "clip.mp4", { type: "video/mp4" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/can't be attached/i);
    expect(sendButton()).toBeDisabled();

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /remove clip\.mp4/i }));
    });
    expect(sendButton()).not.toBeDisabled();
    act(() => {
      fireEvent.click(sendButton());
    });
    expect(onSend).toHaveBeenCalledWith("see clip", []);
  });

  acceptance("chat", "a pasted image is attached", async () => {
    const image = new File([new Uint8Array(4)], "image.png", { type: "image/png" });
    uploadMock.mockResolvedValue(stored("image.png", "image/png", 4));
    render(<Composer onSend={vi.fn()} />);

    act(() => {
      fireEvent.paste(screen.getByRole("textbox"), {
        clipboardData: { files: [image], getData: () => "" },
      });
    });

    expect(uploadMock).toHaveBeenCalledWith(image, expect.any(AbortSignal));
    expect(screen.getByRole("list", { name: /attached files/i })).toHaveTextContent("image.png");
  });

  test("pasting plain text attaches nothing", () => {
    render(<Composer onSend={vi.fn()} />);
    act(() => {
      fireEvent.paste(screen.getByRole("textbox"), {
        clipboardData: { files: [], getData: () => "hello" },
      });
    });
    expect(uploadMock).not.toHaveBeenCalled();
  });

  test("dropping files on the composer attaches them", () => {
    const doc = new File(["%PDF"], "report.pdf", { type: "application/pdf" });
    uploadMock.mockResolvedValue(stored("report.pdf", "application/pdf", 4));
    render(<Composer onSend={vi.fn()} />);
    const composer = screen.getByTestId("composer");

    act(() => {
      fireEvent.dragOver(composer, { dataTransfer: { types: ["Files"], files: [doc] } });
    });
    expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", "Drop files to attach");
    act(() => {
      fireEvent.drop(composer, { dataTransfer: { types: ["Files"], files: [doc] } });
    });

    expect(uploadMock).toHaveBeenCalledWith(doc, expect.any(AbortSignal));
    expect(screen.getByRole("textbox")).not.toHaveAttribute("placeholder", "Drop files to attach");
  });

  test("a message may carry only attachments", async () => {
    const uploaded = stored("shot.png", "image/png", 3);
    uploadMock.mockResolvedValue(uploaded);
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    expect(sendButton()).toBeDisabled();
    pick(new File(["abc"], "shot.png", { type: "image/png" }));
    await waitFor(() => expect(sendButton()).not.toBeDisabled());
    act(() => {
      fireEvent.click(sendButton());
    });
    expect(onSend).toHaveBeenCalledWith("", [uploaded]);
  });

  test("a file over the limit is refused without uploading", () => {
    const big = new File(["x"], "huge.bin", { type: "image/png" });
    Object.defineProperty(big, "size", { value: 20 * 1024 * 1024 + 1 });
    render(<Composer onSend={vi.fn()} />);
    pick(big);
    expect(uploadMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Over the 20 MB limit");
  });

  test("an eleventh file is refused without uploading", async () => {
    uploadMock.mockImplementation(async (file: File) => stored(file.name, "text/plain", 1));
    render(<Composer onSend={vi.fn()} />);
    const input = screen.getByTestId("composer-file-input");
    const files = Array.from({ length: 11 }, (_, i) => new File(["x"], `f${i}.txt`));
    act(() => {
      fireEvent.change(input, { target: { files } });
    });
    expect(uploadMock).toHaveBeenCalledTimes(10);
    expect(screen.getByRole("alert")).toHaveTextContent("At most 10 files per message");
  });

  test("a chip removed while uploading is not brought back by the upload finishing", async () => {
    let finish: (value: ChatAttachment) => void = () => {};
    uploadMock.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<Composer onSend={vi.fn()} />);
    pick(new File(["x"], "a.txt", { type: "text/plain" }));
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /remove a\.txt/i }));
    });
    await act(async () => {
      finish(stored("a.txt", "text/plain", 1));
    });
    expect(screen.queryByRole("list", { name: /attached files/i })).not.toBeInTheDocument();
  });

  test("removing a chip mid-upload cancels its request and reports nothing", async () => {
    let fail: (err: unknown) => void = () => {};
    uploadMock.mockReturnValue(new Promise((_, reject) => (fail = reject)));
    render(<Composer onSend={vi.fn()} />);
    pick(new File(["x"], "a.txt", { type: "text/plain" }));
    const signal = uploadMock.mock.calls[0][1]!;
    expect(signal.aborted).toBe(false);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /remove a\.txt/i }));
    });
    expect(signal.aborted).toBe(true);
    await act(async () => {
      fail(new DOMException("aborted", "AbortError"));
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: /attached files/i })).not.toBeInTheDocument();
  });

  test("a refused file does not take one of the ten slots", () => {
    uploadMock.mockImplementation(async (file: File) => stored(file.name, "text/plain", 1));
    render(<Composer onSend={vi.fn()} />);
    const big = new File(["x"], "huge.bin");
    Object.defineProperty(big, "size", { value: 20 * 1024 * 1024 + 1 });
    const valid = Array.from({ length: 10 }, (_, i) => new File(["x"], `f${i}.txt`));
    act(() => {
      fireEvent.change(screen.getByTestId("composer-file-input"), {
        target: { files: [big, ...valid] },
      });
    });
    expect(uploadMock).toHaveBeenCalledTimes(10);
    expect(screen.getAllByRole("alert")).toHaveLength(1);

    pick(new File(["x"], "eleventh.txt"));
    expect(uploadMock).toHaveBeenCalledTimes(10);
    expect(screen.getAllByRole("alert")[1]).toHaveTextContent("At most 10 files per message");
  });

  test("chips survive a refused send and clear after an accepted one", async () => {
    const uploaded = stored("shot.png", "image/png", 3);
    uploadMock.mockResolvedValue(uploaded);
    const onSend = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    render(<Composer onSend={onSend} />);
    pick(new File(["abc"], "shot.png", { type: "image/png" }));
    await waitFor(() => expect(sendButton()).not.toBeDisabled());

    await act(async () => {
      fireEvent.click(sendButton());
    });
    expect(onSend).toHaveBeenLastCalledWith("", [uploaded]);
    expect(screen.getByRole("list", { name: /attached files/i })).toHaveTextContent("shot.png");
    expect(sendButton()).not.toBeDisabled();

    await act(async () => {
      fireEvent.click(sendButton());
    });
    expect(onSend).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("list", { name: /attached files/i })).not.toBeInTheDocument();
  });

  test("a file dropped on a disabled composer is claimed but not attached", () => {
    render(<Composer onSend={vi.fn()} disabled />);
    const composer = screen.getByTestId("composer");
    const doc = new File(["%PDF"], "report.pdf", { type: "application/pdf" });
    const dataTransfer = { types: ["Files"], files: [doc] };

    const over = createEvent.dragOver(composer, { dataTransfer });
    const drop = createEvent.drop(composer, { dataTransfer });
    act(() => {
      fireEvent(composer, over);
      fireEvent(composer, drop);
    });
    expect(over.defaultPrevented).toBe(true);
    expect(drop.defaultPrevented).toBe(true);
    expect(uploadMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("list", { name: /attached files/i })).not.toBeInTheDocument();
  });

  test("crossing a child element keeps the drop highlight", () => {
    render(<Composer onSend={vi.fn()} />);
    const composer = screen.getByTestId("composer");
    const textbox = screen.getByRole("textbox");
    const dataTransfer = { types: ["Files"], files: [] };
    act(() => {
      fireEvent.dragEnter(composer, { dataTransfer });
      fireEvent.dragEnter(textbox, { dataTransfer });
      fireEvent.dragLeave(composer, { dataTransfer });
    });
    expect(textbox).toHaveAttribute("placeholder", "Drop files to attach");
    act(() => {
      fireEvent.dragLeave(textbox, { dataTransfer });
    });
    expect(textbox).not.toHaveAttribute("placeholder", "Drop files to attach");
  });

  test("the attach button is disabled with the composer", () => {
    render(<Composer onSend={vi.fn()} disabled />);
    expect(screen.getByRole("button", { name: /attach files/i })).toBeDisabled();
  });
});
