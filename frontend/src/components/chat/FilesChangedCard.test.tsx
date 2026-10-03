import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { FilesChangedCard } from "./FilesChangedCard";
import type { ReplyFile } from "@/lib/api/chat";

vi.mock("@/lib/api/chat", () => ({
  chatApi: { listReplyFiles: vi.fn(), getAgentConfig: vi.fn() },
}));
const { chatApi } = await import("@/lib/api/chat");
const api = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const estimate = [{ path: "/w/old.py", added: 1, removed: 0 }];

function renderCard(props: Partial<React.ComponentProps<typeof FilesChangedCard>> = {}) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <FilesChangedCard conversationId="c1" messageId="m1" estimate={estimate} {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.getAgentConfig.mockResolvedValue({ cwd: "/w" });
});

describe("FilesChangedCard", () => {
  test("shows the recorded files relative to the working folder; rows with a diff open it", async () => {
    const files: ReplyFile[] = [
      { path: "/w/src/a.py", added: 12, removed: 3, has_diff: true },
      { path: "/w/big.bin", added: 0, removed: 0, has_diff: false },
    ];
    api.listReplyFiles.mockResolvedValue(files);
    const onOpenFile = vi.fn();
    renderCard({ onOpenFile, selectedPath: "/w/src/a.py" });
    const row = await screen.findByRole("button", { name: /src\/a\.py/ });
    expect(row).toHaveAttribute("aria-current", "true");
    expect(screen.getByText("big.bin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /big\.bin/ })).not.toBeInTheDocument();
    expect(screen.queryByText("old.py")).not.toBeInTheDocument();
    fireEvent.click(row);
    expect(onOpenFile).toHaveBeenCalledWith("/w/src/a.py");
  });

  test("an older reply with no recorded files keeps the tool-call estimate, without a diff", async () => {
    api.listReplyFiles.mockResolvedValue([]);
    renderCard();
    expect(await screen.findByText("old.py")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("nothing renders when neither source has a file", () => {
    api.listReplyFiles.mockResolvedValue([]);
    const { container } = renderCard({ estimate: [] });
    expect(container).toBeEmptyDOMElement();
  });
});
