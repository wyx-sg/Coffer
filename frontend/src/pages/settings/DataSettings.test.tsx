// frontend/src/pages/settings/DataSettings.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { components } from "@/lib/api/types";
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

type Policy = components["schemas"]["RetentionPolicyOut"];

const POLICIES: Policy[] = [
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
    table_name: "attachments",
    display_name: "Attachments",
    description: "x",
    default_retention_days: 30,
    retention_days: 30,
    last_pruned_at: null,
    last_pruned_rows: 0,
  },
  {
    table_name: "skill_data",
    display_name: "Skill working files",
    description: "x",
    default_retention_days: 30,
    retention_days: 30,
    last_pruned_at: null,
    last_pruned_rows: 0,
  },
  {
    table_name: "config_backups",
    display_name: "Config backups",
    description: "x",
    default_retention_days: 30,
    retention_days: 30,
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
  history: { path: "/Users/u/.coffer/runs.db", bytes: 50_541_363 },
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>{ui}</ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

function mockApi({
  storage = STORAGE,
  policies = POLICIES,
  patch = vi.fn().mockResolvedValue({ data: {}, error: undefined }),
  post = vi.fn().mockResolvedValue({ data: { tables: { mcp_invocations: 12 } }, error: undefined }),
}: {
  storage?: typeof STORAGE;
  policies?: typeof POLICIES;
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
          : { data: { policies }, error: undefined },
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
    expect(within(vault).getByRole("button", { name: /open folder/i })).toBeInTheDocument();
    const local = screen.getByTestId("settings-data-local");
    expect(
      await within(local).findByText("Attachments are deleted automatically after 30 days."),
    ).toBeInTheDocument();
    // The folder is named in the button's tooltip, not in a Location row.
    expect(within(local).queryByText("~/.coffer/chat-media")).toBeNull();
    expect(within(local).getByRole("button", { name: /open folder/i })).toBeInTheDocument();
    const history = screen.getByTestId("settings-data-history");
    expect(within(history).getByText("48.2 MB")).toBeInTheDocument();
    expect(await within(history).findByText("Changes")).toBeInTheDocument();
    expect(within(history).getByText("Tool calls")).toBeInTheDocument();
    // Conversations are not a record kind any more: Coffer keeps no conversation text.
    expect(within(history).queryByText("Conversations")).toBeNull();
    expect(within(history).getByText("Skill working files")).toBeInTheDocument();
    expect(within(history).getByText("Config backups")).toBeInTheDocument();
    // Only the four record kinds; the other pruned tables keep their defaults.
    expect(within(history).queryByText("Sync rounds")).toBeNull();
    expect(within(history).queryByText("Attachments")).toBeNull();
    expect(within(history).getByRole("button", { name: /clear expired data now/i })).toBeVisible();
    // Coffer keeps no rebuildable cache: no cache block and no Clear cache.
    expect(screen.queryByTestId("settings-data-cache")).toBeNull();
    expect(screen.queryByText("Rebuildable cache")).toBeNull();
    expect(screen.queryByText(/this mac only/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /^save$/i })).toBeNull();
  });

  acceptance(
    "web-ui",
    "the attachments retention is set where the attachments are listed",
    async () => {
      const { patch } = mockApi();
      render(wrap(<DataSettings />));
      const local = await screen.findByTestId("settings-data-local");
      expect(await within(local).findByText("Attachments")).toBeInTheDocument();
      expect(
        within(screen.getByTestId("settings-data-history")).queryByText("Attachments"),
      ).toBeNull();
      expect(
        await within(local).findByText("Attachments are deleted automatically after 30 days."),
      ).toBeInTheDocument();
      fireEvent.click(within(local).getByRole("switch", { name: /keep forever/i }));
      await waitFor(() =>
        expect(patch).toHaveBeenCalledWith("/retention/policies/{table_name}", {
          params: { path: { table_name: "attachments" } },
          body: { retention_days: null },
        }),
      );
    },
  );

  test("attachments kept forever fall back to the backup line; shortening counts files", async () => {
    const policies = POLICIES.map((p) =>
      p.table_name === "attachments" ? { ...p, retention_days: null } : p,
    );
    mockApi({ policies });
    render(wrap(<DataSettings />));
    const local = await screen.findByTestId("settings-data-local");
    expect(
      await within(local).findByText("Include this folder in your own backups."),
    ).toBeInTheDocument();
    fireEvent.click(await within(local).findByRole("switch", { name: /keep forever/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Keep attachments for 30 days?")).toBeInTheDocument();
    expect(await within(dialog).findByText(/4 files/)).toBeInTheDocument();
  });

  acceptance("web-ui", "skill working files are kept for a chosen window", async () => {
    mockApi();
    render(wrap(<DataSettings />));
    const history = await screen.findByTestId("settings-data-history");
    const labels = (await within(history).findAllByText(/^(Tool calls|Skill working files)$/)).map(
      (el) => el.textContent,
    );
    expect(labels).toEqual(["Tool calls", "Skill working files"]);
    // Shortening 30 days asks first and counts files.
    // The second-to-last number field in History is the Skill working files row.
    const input = within(history).getAllByRole("spinbutton").at(-2) as HTMLElement;
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.blur(input);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Keep skill working files for 7 days?")).toBeInTheDocument();
    expect(await within(dialog).findByText(/4 files/)).toBeInTheDocument();
  });

  acceptance("web-ui", "config backups are kept for a chosen window", async () => {
    mockApi();
    render(wrap(<DataSettings />));
    const history = await screen.findByTestId("settings-data-history");
    const labels = (
      await within(history).findAllByText(/^(Skill working files|Config backups)$/)
    ).map((el) => el.textContent);
    expect(labels).toEqual(["Skill working files", "Config backups"]);
    expect(
      within(history).getByText(/newest backup of each file is always kept/i),
    ).toBeInTheDocument();
    // The last number field in History is the Config backups row.
    const input = within(history).getAllByRole("spinbutton").at(-1) as HTMLElement;
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.blur(input);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Keep config backups for 7 days?")).toBeInTheDocument();
    expect(await within(dialog).findByText(/4 files/)).toBeInTheDocument();
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
    await within(vault).findByText("12.4 MB · 1,382 versions");
    fireEvent.click(within(vault).getByRole("button", { name: /open folder/i }));
    expect(fsApi.open).toHaveBeenCalledWith("/Users/u/.coffer/vault", undefined);
  });

  test("the vault block shows its size and versions, as drawn", async () => {
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
    expect(await screen.findByText("Removed 12 rows from Tool calls")).toBeInTheDocument();
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
    expect(failed).toHaveTextContent("Tool calls are still kept forever.");
    expect(screen.getByText("Not saved")).toBeInTheDocument();
    expect(screen.queryByTestId("settings-data-other-retention")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
  });
});
