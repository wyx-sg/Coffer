// frontend/src/pages/MachinesPage.test.tsx
//
// Machines fleet view (spec 010-sync amendment, ADR-045). We mock the
// machines + sync hooks so the page doesn't depend on a running daemon.
//
// Carries the acceptance marker for spec scenario "machines are visible
// after they sync".

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { MachinesPage } from "./MachinesPage";
import { acceptance } from "@/test/acceptance";
import type { SyncMachine } from "@/lib/hooks/useMachines";
import type { SyncStatus } from "@/lib/hooks/useSync";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: vi.fn(),
}));
vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: vi.fn(),
  useRunSync: vi.fn(),
  useRenameMachine: vi.fn(),
}));

const machinesHooks = await import("@/lib/hooks/useMachines");
const syncHooks = await import("@/lib/hooks/useSync");
const useMachinesMock = vi.mocked(machinesHooks.useMachines);
const useSyncStatusMock = vi.mocked(syncHooks.useSyncStatus);
const useRunSyncMock = vi.mocked(syncHooks.useRunSync);
const useRenameMachineMock = vi.mocked(syncHooks.useRenameMachine);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const LOCAL: SyncMachine = {
  machine_id: "01AAAAAAAAAAAAAAAAAAAAAAAA",
  display_name: "studio",
  platform: "darwin",
  os_version: "25.5.0",
  coffer_version: "0.1.1",
  last_sync_at: "2026-07-10T12:00:00+00:00",
  is_local: true,
};

const OTHER: SyncMachine = {
  machine_id: "01BBBBBBBBBBBBBBBBBBBBBBBB",
  display_name: "laptop",
  platform: "darwin",
  os_version: "24.0.0",
  coffer_version: "0.1.1",
  last_sync_at: null,
  is_local: false,
};

const CLEAN_STATUS: SyncStatus = {
  status: "clean",
  last_sync_at: "2026-07-10T12:00:00+00:00",
  last_error: null,
  error_hint: null,
  conflict_paths: [],
  locked_refs: [],
  quarantined_refs: [],
};

const runMutate = vi.fn();

function stubHooks(opts: { data?: unknown; isPending?: boolean; error?: unknown }) {
  useMachinesMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
    refetch: vi.fn().mockResolvedValue({}),
  } as unknown as ReturnType<typeof machinesHooks.useMachines>);
  useSyncStatusMock.mockReturnValue({
    data: CLEAN_STATUS,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof syncHooks.useSyncStatus>);
  useRunSyncMock.mockReturnValue({
    mutate: runMutate,
    isPending: false,
  } as unknown as ReturnType<typeof syncHooks.useRunSync>);
  useRenameMachineMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof syncHooks.useRenameMachine>);
}

afterEach(() => vi.clearAllMocks());

acceptance("010-sync", "machines are visible after they sync", async () => {
  stubHooks({ data: { machines: [LOCAL, OTHER] } });
  render(<MachinesPage />, { wrapper: wrap(null) });

  // Title renders.
  expect(screen.getByRole("heading", { name: /machines/i })).toBeInTheDocument();

  // A card per machine, with the local one badged.
  expect(screen.getByText(/this machine/i)).toBeInTheDocument();
  expect(screen.getByText("laptop")).toBeInTheDocument();

  // Each card links to its detail route.
  const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
  expect(links).toContain(`/machines/${LOCAL.machine_id}`);
  expect(links).toContain(`/machines/${OTHER.machine_id}`);
});

describe("MachinesPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("status strip shows the sync state and the run button fires the mutation", () => {
    stubHooks({ data: { machines: [LOCAL] } });
    render(<MachinesPage />, { wrapper: wrap(null) });
    expect(screen.getByRole("status")).toHaveTextContent(/in sync/i);
    fireEvent.click(screen.getByRole("button", { name: /sync now/i }));
    expect(runMutate).toHaveBeenCalled();
  });

  test("status strip links to the sync settings page", () => {
    stubHooks({ data: { machines: [LOCAL] } });
    render(<MachinesPage />, { wrapper: wrap(null) });
    const configureLink = screen.getByRole("link", { name: /configure/i });
    expect(configureLink).toHaveAttribute("href", "/settings/sync");
  });

  test("renders the loading state when the query is pending", () => {
    stubHooks({ isPending: true });
    render(<MachinesPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the error card when the query errors", () => {
    stubHooks({ error: new ApiError("BOOM", "kaboom") });
    render(<MachinesPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/failed to load machines/i)).toBeInTheDocument();
    expect(screen.getByText("kaboom")).toBeInTheDocument();
  });

  test("renders an empty state when no machines are known", () => {
    stubHooks({ data: { machines: [] } });
    render(<MachinesPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/no machines/i)).toBeInTheDocument();
  });
});
