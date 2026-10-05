// src/components/shell/useTrayAttentionCount.test.tsx — the tray count follows the attention list.
import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { attentionKey } from "@/lib/api/queryKeys";
import { useTrayAttentionCount } from "./useTrayAttentionCount";

const read = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/attention", () => ({ attentionApi: { read } }));
const shell = vi.hoisted(() => ({ inShell: true, report: vi.fn(() => Promise.resolve()) }));
vi.mock("@/lib/tauri", () => ({
  inDesktopShell: () => shell.inShell,
  setShellAttentionCount: shell.report,
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
    shell.report.mockClear();
    read.mockResolvedValueOnce(listOf(2)).mockResolvedValue(listOf(0));
    const { qc, wrapper } = harness();
    renderHook(() => useTrayAttentionCount(), { wrapper });
    await waitFor(() => expect(shell.report).toHaveBeenLastCalledWith(2));
    // A resolve anywhere invalidates the shared key.
    await act(() => qc.invalidateQueries({ queryKey: attentionKey }));
    await waitFor(() => expect(shell.report).toHaveBeenLastCalledWith(0));
  });

  it("reads nothing in a browser", async () => {
    shell.inShell = false;
    shell.report.mockClear();
    read.mockClear();
    const { wrapper } = harness();
    renderHook(() => useTrayAttentionCount(), { wrapper });
    await new Promise((r) => setTimeout(r, 20));
    expect(read).not.toHaveBeenCalled();
    expect(shell.report).not.toHaveBeenCalled();
  });
});
