// components/chat/ThreadAttachment.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ThreadAttachment } from "./ThreadAttachment";
import { chatApi } from "@/lib/api/chat";
import { contentBlock } from "@/lib/chat/contentBlock";
import { acceptance } from "@/test/acceptance";

const image = contentBlock({
  type: "attachment",
  filename: "shot.png",
  mime: "image/png",
  attachment_id: "a".repeat(32),
  size: 2048,
});

describe("ThreadAttachment", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:thumb");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  acceptance(
    "chat",
    "an attached image is fetched by its id for the thread's thumbnail",
    async () => {
      const fetchBlob = vi
        .spyOn(chatApi, "attachmentBlob")
        .mockResolvedValue(new Blob(["x"], { type: "image/png" }));
      render(<ThreadAttachment conversationId="c-1" block={image} />);
      const img = await screen.findByTestId("attachment-thumbnail");
      expect(img).toHaveAttribute("src", "blob:thumb");
      expect(fetchBlob).toHaveBeenCalledWith("c-1", "a".repeat(32));
    },
  );

  test("a pruned image stays a chip with its type and size", async () => {
    const fetchBlob = vi.spyOn(chatApi, "attachmentBlob").mockRejectedValue(new Error("404"));
    render(<ThreadAttachment conversationId="c-1" block={image} />);
    await waitFor(() => expect(fetchBlob).toHaveBeenCalled());
    expect(screen.getByTestId("attachment-chip")).toHaveTextContent("shot.png");
    expect(screen.getByTestId("attachment-chip")).toHaveTextContent("image/png · 2 KB");
    expect(screen.queryByTestId("attachment-thumbnail")).toBeNull();
  });

  test("a reference without an id keeps the plain chip and fetches nothing", () => {
    const fetchBlob = vi.spyOn(chatApi, "attachmentBlob");
    render(
      <ThreadAttachment
        conversationId="c-1"
        block={contentBlock({ type: "attachment", filename: "old.png", mime: "image/png" })}
      />,
    );
    expect(screen.getByTestId("attachment-chip")).toHaveTextContent("old.png");
    expect(fetchBlob).not.toHaveBeenCalled();
  });
});
