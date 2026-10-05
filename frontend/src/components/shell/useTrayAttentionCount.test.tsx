// src/components/shell/useTrayAttentionCount.test.tsx — the tray count follows the attention list.
import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { attentionKey } from "@/lib/api/queryKeys";
import { useTrayAttentionCount } from "./useTrayAttentionCount";

const read = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/attention", () => ({ attentionApi: { read } }));
// The change feed: the test plays the daemon and hands the hook its events.
const feed = vi.hoisted(() => ({
  follow: vi.fn<(listener: (m: unknown) => void, signal: AbortSignal) => Promise<void>>(),
}));
vi.mock("@/lib/events/eventStream", () => ({ followDaemonEvents: feed.follow }));
const shell = vi.hoisted(() => ({
  inShell: true,
  invoke: vi.fn<(command: string, args?: { count: number }) => Promise<void>>(() =>
    Promise.resolve(),
  ),
}));
vi.mock("@/lib/tauri", () => ({
  inDesktopShell: () => shell.inShell,
  shellInvoke: shell.invoke,
}));

function harness() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const listOf = (n: number) => ({
  items: Array.from({ length: n }, (_, i) => ({ kind: "mcp_server", uid: `u${i}` })),
  errors: [],
});

describe("useTrayAttentionCount", () => {
  it("reports the list's length, and again when a resolve shrinks it to nothing", async () => {
    shell.inShell = true;
    shell.invoke.mockClear();
    read.mockResolvedValueOnce(listOf(2)).mockResolvedValue(listOf(0));
    const { qc, wrapper } = harness();
    renderHook(() => useTrayAttentionCount(), { wrapper });
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenLastCalledWith("set_attention_count", { count: 2 }),
    );
    // A resolve anywhere invalidates the shared key.
    await act(() => qc.invalidateQueries({ queryKey: attentionKey }));
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenLastCalledWith("set_attention_count", { count: 0 }),
    );
  });

  it("reads nothing in a browser", async () => {
    shell.inShell = false;
    shell.invoke.mockClear();
    read.mockClear();
    const { wrapper } = harness();
    renderHook(() => useTrayAttentionCount(), { wrapper });
    await new Promise((r) => setTimeout(r, 20));
    expect(read).not.toHaveBeenCalled();
    expect(shell.invoke).not.toHaveBeenCalled();
  });

  it("follows the change feed instead of polling: an attention change re-reads the list", async () => {
    shell.inShell = true;
    shell.invoke.mockClear();
    let emit: (m: unknown) => void = () => {};
    feed.follow.mockImplementation((listener) => {
      emit = listener;
      return new Promise(() => {});
    });
    read.mockReset();
    read.mockResolvedValueOnce(listOf(1)).mockResolvedValue(listOf(3));
    const { wrapper } = harness();
    renderHook(() => useTrayAttentionCount(), { wrapper });
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenLastCalledWith("set_attention_count", { count: 1 }),
    );
    act(() =>
      emit({ type: "change", change: { seq: 1, kind: "attention", id: null, op: "upsert" } }),
    );
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenLastCalledWith("set_attention_count", { count: 3 }),
    );
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("opens no change feed in a browser", () => {
    shell.inShell = false;
    feed.follow.mockClear();
    const { wrapper } = harness();
    renderHook(() => useTrayAttentionCount(), { wrapper });
    expect(feed.follow).not.toHaveBeenCalled();
  });
});
