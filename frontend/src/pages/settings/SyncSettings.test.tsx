// frontend/src/pages/settings/SyncSettings.test.tsx
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SyncSettings } from "./SyncSettings";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncConfig: vi.fn(),
  useSyncStatus: vi.fn(),
  useUpdateSyncConfig: vi.fn(),
  useRunSync: vi.fn(),
  useImportMasterKey: vi.fn(),
  useExportMasterKey: vi.fn(),
  useKeyFingerprint: vi.fn(),
  useSyncMachines: vi.fn(),
  useRenameMachine: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useSync");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const update = vi.fn();
const run = vi.fn();

afterEach(() => vi.clearAllMocks());

type Status = ReturnType<typeof hooks.useSyncStatus>["data"];

function seed(statusValue: NonNullable<Status>["status"], over: Partial<NonNullable<Status>> = {}) {
  vi.mocked(hooks.useSyncConfig).mockReturnValue({
    data: {
      remote: "git@github.com:me/v.git",
      branch: "main",
      enabled: true,
      auto: false,
      interval_seconds: 300,
      poll_remote_seconds: 15,
    },
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useSyncConfig>);
  vi.mocked(hooks.useSyncStatus).mockReturnValue({
    data: {
      status: statusValue,
      last_sync_at: null,
      last_error: null,
      error_hint: null,
      conflict_paths: [],
      locked_refs: [],
      quarantined_refs: [],
      ...over,
    },
  } as unknown as ReturnType<typeof hooks.useSyncStatus>);
  vi.mocked(hooks.useUpdateSyncConfig).mockReturnValue({
    mutate: update,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useUpdateSyncConfig>);
  vi.mocked(hooks.useRunSync).mockReturnValue({
    mutate: run,
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useRunSync>);
  vi.mocked(hooks.useImportMasterKey).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useImportMasterKey>);
  vi.mocked(hooks.useExportMasterKey).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useExportMasterKey>);
  vi.mocked(hooks.useKeyFingerprint).mockReturnValue({
    data: { present: true, fingerprint: "abc123def456" },
  } as unknown as ReturnType<typeof hooks.useKeyFingerprint>);
  vi.mocked(hooks.useSyncMachines).mockReturnValue({
    data: { machines: [] },
  } as unknown as ReturnType<typeof hooks.useSyncMachines>);
  vi.mocked(hooks.useRenameMachine).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useRenameMachine>);
}

describe("SyncSettings", () => {
  test("auto-saves (no Save button) — editing the remote and blurring PUTs the config", () => {
    seed("clean");
    render(<SyncSettings />, { wrapper: wrap });
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    const remote = screen.getByRole("textbox");
    fireEvent.change(remote, { target: { value: "git@github.com:me/other.git" } });
    fireEvent.blur(remote);
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        remote: "git@github.com:me/other.git",
        branch: "main",
        enabled: true,
      }),
    );
  });

  test("toggling a switch auto-saves the new value", () => {
    seed("clean");
    render(<SyncSettings />, { wrapper: wrap });
    // Two switches (enable, auto); auto starts false → toggling it PUTs auto:true.
    fireEvent.click(screen.getAllByRole("switch")[1]);
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ auto: true }));
  });

  test("sync now triggers a run", () => {
    seed("clean");
    render(<SyncSettings />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /sync now/i }));
    expect(run).toHaveBeenCalled();
  });

  test("a failed sync run surfaces its error", () => {
    seed("clean");
    vi.mocked(hooks.useRunSync).mockReturnValue({
      mutate: run,
      isPending: false,
      error: new Error("boom"),
    } as unknown as ReturnType<typeof hooks.useRunSync>);
    render(<SyncSettings />, { wrapper: wrap });
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  test("an auth failure renders configuration guidance, not just raw stderr", () => {
    seed("error", {
      last_error: "git fetch failed: fatal: could not read Username",
      error_hint: "auth",
    });
    render(<SyncSettings />, { wrapper: wrap });
    // Raw error stays for diagnosis; the actionable hint is what the user acts on.
    expect(screen.getByText(/could not read username/i)).toBeInTheDocument();
    expect(screen.getByText(/ssh/i)).toBeInTheDocument();
  });

  test("conflicts auto-resolve: no resolution panel; a parked conflict points at the repo", () => {
    seed("conflicted", { conflict_paths: ["resources/mcp_server/x.yaml"] });
    render(<SyncSettings />, { wrapper: wrap });
    // The ours/theirs panel is gone (auto-resolve owns conflicts now).
    expect(
      screen.queryByRole("button", { name: /keep the remote version/i }),
    ).not.toBeInTheDocument();
    // Fallback guidance: resolve in your own git repo.
    expect(screen.getByText(/could not settle this conflict automatically/i)).toBeInTheDocument();
  });

  test("the master-key card shows the key fingerprint", () => {
    seed("clean");
    render(<SyncSettings />, { wrapper: wrap });
    expect(screen.getByTestId("key-fingerprint")).toHaveTextContent("abc123def456");
  });
});
