import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { DiffDrawer } from "./DiffDrawer";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/chat", () => ({
  chatApi: { listReplyFiles: vi.fn(), getReplyFileDiff: vi.fn(), getAgentConfig: vi.fn() },
}));
const { chatApi } = await import("@/lib/api/chat");
const api = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const DIFFS: Record<string, string> = {
  "/w/a.py": "@@ -1,2 +1,2 @@ def f\n keep\n-old\n+new\n",
  "/w/b.py": "@@ -0,0 +1,1 @@\n+hello\n",
};

function Harness({ onClose }: { onClose: () => void }) {
  const [path, setPath] = useState("/w/a.py");
  return (
    <DiffDrawer
      conversationId="c1"
      messageId="m1"
      path={path}
      onPathChange={setPath}
      onClose={onClose}
    />
  );
}

const renderDrawer = (onClose = vi.fn()) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Harness onClose={onClose} />
    </QueryClientProvider>,
  );

beforeEach(() => {
  api.getAgentConfig.mockResolvedValue({ cwd: "/w" });
  api.listReplyFiles.mockResolvedValue([
    { path: "/w/a.py", added: 1, removed: 1, has_diff: true },
    { path: "/w/skip.bin", added: 0, removed: 0, has_diff: false },
    { path: "/w/b.py", added: 1, removed: 0, has_diff: true },
  ]);
  api.getReplyFileDiff.mockImplementation((_c: string, _m: string, path: string) =>
    Promise.resolve({
      path,
      added: 1,
      removed: 0,
      diff: DIFFS[path] ?? null,
      diff_omitted: DIFFS[path] ? null : "too_large",
    }),
  );
});

describe("DiffDrawer", () => {
  acceptance("chat", "the drawer walks the reply's files", async () => {
    const onClose = vi.fn();
    renderDrawer(onClose);
    expect(await screen.findByText("1 of 2")).toBeInTheDocument();
    expect(await screen.findByText("@@ -1,2 +1,2 @@ def f")).toBeInTheDocument();
    expect(screen.getByText("new")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous file" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next file" }));
    expect(await screen.findByText("2 of 2")).toBeInTheDocument();
    expect(await screen.findByText("hello")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next file" })).toBeDisabled();

    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  test("a file left out of the record says why", async () => {
    api.listReplyFiles.mockResolvedValue([
      { path: "/w/huge.txt", added: 5, removed: 0, has_diff: true },
    ]);
    api.getReplyFileDiff.mockResolvedValue({
      path: "/w/huge.txt",
      added: 5,
      removed: 0,
      diff: null,
      diff_omitted: "too_large",
    });
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <DiffDrawer
          conversationId="c1"
          messageId="m1"
          path="/w/huge.txt"
          onPathChange={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(
      await screen.findByText("This file is too large to show (over 1 MB)"),
    ).toBeInTheDocument();
  });

  test("a failed read offers Retry in the drawer", async () => {
    api.getReplyFileDiff.mockRejectedValueOnce(new Error("boom"));
    renderDrawer();
    const retry = await screen.findByRole("button", { name: "Retry" });
    fireEvent.click(retry);
    expect(await screen.findByText("new")).toBeInTheDocument();
  });
});
