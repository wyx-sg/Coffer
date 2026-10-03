// frontend/src/pages/settings/DataSettings.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import type { StorageSummary } from "@/lib/hooks/useStorage";
import { acceptance } from "@/test/acceptance";

import { DataSettings } from "./DataSettings";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    open: vi.fn().mockResolvedValue(undefined),
    reveal: vi.fn().mockResolvedValue(undefined),
  },
}));

const { getApiClient } = await import("@/lib/api/client");
const { fsApi } = await import("@/lib/api/fs");
const getApiClientMock = vi.mocked(getApiClient);

const POLICIES = [
  {
    table_name: "audit_log",
    display_name: "Audit log",
    description: "x",
    default_retention_days: 365,
    retention_days: 365,
    last_pruned_at: "2026-09-30T03:00:00Z",
    last_pruned_rows: 1000,
  },
  {
    table_name: "mcp_invocations",
    display_name: "MCP Invocations",
    description: "x",
    default_retention_days: 30,
    retention_days: null,
    last_pruned_at: "2026-09-30T03:00:00Z",
    last_pruned_rows: 284,
  },
  {
    table_name: "conversations",
    display_name: "Delete archived chats",
    description: "x",
    default_retention_days: 30,
    retention_days: 90,
    last_pruned_at: null,
    last_pruned_rows: 0,
  },
  {
    table_name: "sync_runs",
    display_name: "Sync rounds",
    description: "x",
    default_retention_days: 90,
    retention_days: 90,
    last_pruned_at: null,
    last_pruned_rows: 0,
  },
];

const STORAGE: StorageSummary = {
  vault: {
    path: "/Users/u/.coffer/vault",
    bytes: 13_002_342,
    versions: 1382,
  },
  local_content: {
    folder: "/Users/u/.coffer",
    locations: ["/Users/u/.coffer/chat-media", "/Users/u/.coffer/channel-media"],
    bytes: 224_395_264,
  },
  history: { path: "/Users/u/.coffer/coffer.db", bytes: 50_541_363 },
  cache: { bytes: 100_663_296 },
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  );
}

function mockApi({
  storage = STORAGE,
  patch = vi.fn().mockResolvedValue({ data: {}, error: undefined }),
  post = vi
    .fn()
    .mockImplementation(async (path: string) =>
      path === "/storage/cache/clear"
        ? { data: { cleared_bytes: 100_663_296 }, error: undefined }
        : { data: { tables: { mcp_invocations: 12 } }, error: undefined },
    ),
}: {
  storage?: typeof STORAGE;
  patch?: ReturnType<typeof vi.fn>;
  post?: ReturnType<typeof vi.fn>;
} = {}) {
  const get = vi
    .fn()
    .mockImplementation(async (path: string) =>
      path === "/storage"
        ? { data: storage, error: undefined }
        : path === "/retention/policies/{table_name}/preview"
          ? { data: { table_name: "mcp_invocations", days: 30, total_rows: 10, rows_to_delete: 4 } }
          : { data: { policies: POLICIES }, error: undefined },
    );
  getApiClientMock.mockReturnValue({ GET: get, POST: post, PATCH: patch } as unknown as ReturnType<
    typeof getApiClient
  >);
  return { get, patch, post };
}

describe("DataSettings", () => {
  beforeEach(() => vi.clearAllMocks());

  acceptance("web-ui", "the data tab shows four blocks and no this-mac block", async () => {
    mockApi();
    render(wrap(<DataSettings />));
    const vault = await screen.findByTestId("settings-data-vault");
    await within(vault).findByText("12.4 MB · 1,382 versions");
    expect(within(vault).getByText("~/.coffer/vault")).toBeInTheDocument();
    expect(within(vault).getByRole("button", { name: /open folder/i })).toBeInTheDocument();
    const local = screen.getByTestId("settings-data-local");
    expect(screen.getByText(/not synced — back it up yourself/i)).toBeInTheDocument();
    expect(within(local).getByText("~/.coffer/chat-media")).toBeInTheDocument();
    expect(within(local).getByRole("button", { name: /open folder/i })).toBeInTheDocument();
    const history = screen.getByTestId("settings-data-history");
    expect(within(history).getByText("48.2 MB")).toBeInTheDocument();
    expect(await within(history).findByText("Changes")).toBeInTheDocument();
    expect(within(history).getByText("MCP calls")).toBeInTheDocument();
    expect(within(history).getByText("Conversations")).toBeInTheDocument();
    // Only the three record kinds; the other pruned tables keep their defaults.
    expect(within(history).queryByText("Sync rounds")).toBeNull();
    expect(within(history).getByRole("button", { name: /clear expired data now/i })).toBeVisible();
    const cache = screen.getByTestId("settings-data-cache");
    expect(within(cache).getByText("96 MB")).toBeInTheDocument();
    expect(within(cache).getByRole("button", { name: /^clear$/i })).toBeInTheDocument();
    expect(screen.queryByText(/this mac only/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /^save$/i })).toBeNull();
  });

  test("the history footer names the last nightly clear", async () => {
    mockApi();
    render(wrap(<DataSettings />));
    expect(await screen.findByText(/last cleared .* — 1284 rows/i)).toBeInTheDocument();
  });

  test("Open folder opens the vault's folder through the daemon", async () => {
    mockApi();
    render(wrap(<DataSettings />));
    const vault = await screen.findByTestId("settings-data-vault");
    await within(vault).findByText("~/.coffer/vault");
    fireEvent.click(within(vault).getByRole("button", { name: /open folder/i }));
    expect(fsApi.open).toHaveBeenCalledWith("/Users/u/.coffer/vault", undefined);
  });

  test("the vault block shows its size, versions and location, as drawn", async () => {
    mockApi();
    render(wrap(<DataSettings />));
    const vault = await screen.findByTestId("settings-data-vault");
    expect(await within(vault).findByText(/1,382 versions/)).toBeInTheDocument();
    expect(screen.getByText(/Synced — a git repository/)).toBeInTheDocument();
    expect(within(vault).queryByText("Latest version")).toBeNull();
  });

  test("a vault not created yet says it becomes a repository at first start", async () => {
    mockApi({
      storage: {
        ...STORAGE,
        vault: {
          path: "/Users/u/.coffer/vault",
          bytes: 0,
          versions: null,
        },
      },
    });
    render(wrap(<DataSettings />));
    await screen.findByTestId("settings-data-vault");
    expect(await screen.findByText(/makes it a git repository/i)).toBeInTheDocument();
  });

  // The page half (the confirmed prune reports what went); the backend half
  // is test_retention_routes.py.
  acceptance("web-ui", "clear expired now removes what retention has passed", async () => {
    const { post } = mockApi();
    render(wrap(<DataSettings />));
    fireEvent.click(await screen.findByRole("button", { name: /clear expired data now/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /clear expired data now/i }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/retention/prune", { body: {} }));
    expect(await screen.findByText("Removed 12 rows from MCP calls")).toBeInTheDocument();
  });

  // The page half; the backend half is test_daemon_port_and_storage_routes.py.
  acceptance("web-ui", "clearing the cache is confirmed and rebuilt", async () => {
    const { post } = mockApi();
    render(wrap(<DataSettings />));
    const cache = await screen.findByTestId("settings-data-cache");
    await within(cache).findByText("96 MB");
    fireEvent.click(within(cache).getByRole("button", { name: /^clear$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/rebuilds memory from the agents' own memory/i),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/sources are gone won't come back/i)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /clear cache/i }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/storage/cache/clear"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("a failed cache clear keeps the dialog open with its error", async () => {
    const post = vi.fn().mockResolvedValue({
      data: undefined,
      error: {
        error: {
          code: "UPKEEP_ALREADY_RUNNING",
          message: "an upkeep pass is already running",
          details: {},
        },
      },
    });
    mockApi({ post });
    render(wrap(<DataSettings />));
    const cache = await screen.findByTestId("settings-data-cache");
    await within(cache).findByText("96 MB");
    fireEvent.click(within(cache).getByRole("button", { name: /^clear$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /clear cache/i }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  test("a retention save that fails says so, marks the row and offers Retry", async () => {
    const patch = vi.fn().mockResolvedValue({
      data: undefined,
      error: { error: { code: "INTERNAL_ERROR", message: "database is locked", details: {} } },
    });
    mockApi({ patch });
    render(wrap(<DataSettings />));
    const forever = await screen.findByRole("switch", { name: /keep forever/i, checked: true });
    fireEvent.click(forever);
    // Turning keep-forever off shortens, so it asks first.
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /shorten/i }));
    const failed = await screen.findByTestId("settings-data-save-failed");
    // The refused save names what is still in place.
    expect(failed).toHaveTextContent("MCP calls are still kept forever.");
    expect(screen.getByText("Not saved")).toBeInTheDocument();
    expect(screen.getByTestId("settings-data-other-retention")).toHaveTextContent(
      "Other retention settings: coffer config",
    );
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
  });
});
