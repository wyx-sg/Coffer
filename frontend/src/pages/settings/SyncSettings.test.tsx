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
  useResolveSync: vi.fn(),
  useImportMasterKey: vi.fn(),
  useExportMasterKey: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useSync");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const update = vi.fn();
const run = vi.fn();
const resolve = vi.fn();

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
    },
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useSyncConfig>);
  vi.mocked(hooks.useSyncStatus).mockReturnValue({
    data: {
      status: statusValue,
      last_sync_at: null,
      last_error: null,
      conflict_paths: [],
      locked_refs: [],
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
  vi.mocked(hooks.useResolveSync).mockReturnValue({
    mutate: resolve,
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useResolveSync>);
  vi.mocked(hooks.useImportMasterKey).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useImportMasterKey>);
  vi.mocked(hooks.useExportMasterKey).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useExportMasterKey>);
}

describe("SyncSettings", () => {
  test("saving PUTs the config", () => {
    seed("clean");
    render(<SyncSettings />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ remote: "git@github.com:me/v.git", branch: "main", enabled: true }),
    );
  });

  test("sync now triggers a run", () => {
    seed("clean");
    render(<SyncSettings />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /sync now/i }));
    expect(run).toHaveBeenCalled();
  });

  test("conflict panel offers ours/theirs resolution", () => {
    seed("conflicted", { conflict_paths: ["resources/mcp_server/x.yaml"] });
    render(<SyncSettings />, { wrapper: wrap });
    expect(screen.getByText("resources/mcp_server/x.yaml")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /keep the remote version/i }));
    expect(resolve).toHaveBeenCalledWith({ strategy: "theirs", paths: [] });
  });
});
