// frontend/src/pages/MemoryPage.test.tsx
//
// The Memory overview (spec memory "Present a partition as its memories",
// web-ui "Show memory delivery on the Memory page"): the per-agent deliveries
// of the last seven days — with no hook detail — above the partitions table,
// or the first-run state while there are none. Only the api module is mocked;
// the real hooks run over a real QueryClient.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { COFFER, DELIVERIES, GLOBAL, GONE } from "@/components/memory/memoryTestData";
import type { DeliveryOverviewOut, PartitionOut } from "@/lib/api/memoryTypes";
import { MemoryPage } from "./MemoryPage";

vi.mock("@/lib/api/memory", () => ({
  listPartitions: vi.fn(),
  getDeliveries: vi.fn(),
  getReading: vi.fn(),
  sync: vi.fn(),
}));
vi.mock("@/lib/api/upkeep", () => ({ listUpkeepRuns: vi.fn() }));
vi.mock("@/lib/api/internalEngine", () => ({ internalEngineApi: { get: vi.fn() } }));
vi.mock("@/lib/api/agents", () => ({ agentsApi: { list: vi.fn() } }));
vi.mock("@/lib/api/agentNativeMemory", () => ({ agentNativeMemoryApi: { list: vi.fn() } }));
const api = await import("@/lib/api/memory");
const { listUpkeepRuns } = await import("@/lib/api/upkeep");
const { internalEngineApi } = await import("@/lib/api/internalEngine");
const { agentsApi } = await import("@/lib/api/agents");
const { agentNativeMemoryApi } = await import("@/lib/api/agentNativeMemory");

const MINUTE = 60_000;
const ago = (minutes: number) => new Date(Date.now() - minutes * MINUTE).toISOString();

function stub(partitions: PartitionOut[], deliveries: DeliveryOverviewOut = DELIVERIES) {
  vi.mocked(api.listPartitions).mockResolvedValue({ partitions });
  vi.mocked(api.getDeliveries).mockResolvedValue(deliveries);
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>
          <MemoryPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("MemoryPage", () => {
  beforeEach(() => {
    vi.mocked(api.listPartitions).mockReset();
    vi.mocked(api.getDeliveries).mockReset();
    vi.mocked(api.getReading).mockResolvedValue({ read_at: ago(14), failures: [] });
    vi.mocked(listUpkeepRuns).mockResolvedValue({ runs: [] });
    vi.mocked(internalEngineApi.get).mockResolvedValue({
      model: "m",
      upkeep: {
        aggregate: {
          enabled: true,
          interval_s: null,
          default_interval_s: 3600,
          last_pass_at: ago(14),
          next_pass_at: new Date(Date.now() + 46 * MINUTE).toISOString(),
        },
        distil: {
          enabled: true,
          interval_s: null,
          default_interval_s: 21600,
          last_pass_at: null,
          next_pass_at: null,
        },
      },
    } as unknown as Awaited<ReturnType<typeof internalEngineApi.get>>);
    vi.mocked(agentsApi.list).mockResolvedValue({ items: [] } as unknown as Awaited<
      ReturnType<typeof agentsApi.list>
    >);
  });

  test("says what memory is, read-only, with one Update memory button", async () => {
    stub([GLOBAL, COFFER]);
    renderPage();
    await screen.findByRole("table");
    expect(
      screen.getByText(/distilled into one memory per subject\. Read-only\./i),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^sync$/i })).toBeNull();
  });

  test("lists deliveries per agent over the last 7 days, with no hook detail", async () => {
    stub([COFFER]);
    renderPage();
    const block = await screen.findByTestId("memory-deliveries");
    expect(within(block).getByText("Delivered at session start")).toBeInTheDocument();
    expect(within(block).getByText("Last 7 days")).toBeInTheDocument();

    const claude = await within(block).findByTestId("memory-delivery-claude_code");
    expect(claude).toHaveTextContent("Claude Code");
    expect(claude).toHaveTextContent(/Delivered 12 times in the last 7 days/);
    expect(claude).toHaveTextContent(/5 memories read/);
    expect(claude).toHaveTextContent(/last /);

    const codex = within(block).getByTestId("memory-delivery-codex");
    expect(codex).toHaveTextContent("Not delivered in the last 7 days");
    // Claude Code is listed first, as on the Agents page.
    const rows = within(block).getAllByRole("listitem");
    expect(rows[0]).toBe(claude);

    // Hook state and Repair live on the agent's page only.
    expect(block).not.toHaveTextContent(/hook|repair|stale|installed/i);
    expect(screen.queryByRole("button", { name: /repair|install/i })).toBeNull();
  });

  test("a read count the daemon cannot compute reads unavailable, never 0", async () => {
    stub([COFFER], {
      window_days: 7,
      agents: [
        {
          ...DELIVERIES.agents[1],
          agent_uid: "ag-codex",
          agent_name: "Codex",
          agent_type: "codex",
          deliveries: 3,
          notes_read: null,
          notes_read_status: "unavailable",
        },
      ],
    });
    renderPage();
    const row = await screen.findByTestId("memory-delivery-codex");
    expect(row).toHaveTextContent(
      /Delivered 3 times in the last 7 days · memories read unavailable/,
    );
    expect(row).not.toHaveTextContent(/0 memories read/);
  });

  test("the header says when memory was last read, beside Automatic and Update memory", async () => {
    stub([COFFER]);
    renderPage();
    expect(await screen.findByTestId("memory-status")).toHaveTextContent(/^Read 14m ago$/);
    expect(await screen.findByTestId("memory-automatic")).toHaveTextContent("Automatic · hourly");
  });

  test("a read that left an agent unread says so in the header and in a banner", async () => {
    stub([COFFER]);
    vi.mocked(api.getReading).mockResolvedValue({
      read_at: ago(2),
      failures: [
        {
          agent: "codex",
          path: "/Users/dev/.codex/memories",
          reason: "not readable",
          last_read_at: "2026-09-27T10:00:00Z",
        },
      ],
    });
    renderPage();
    expect(await screen.findByTestId("memory-status")).toHaveTextContent(/· 1 agent failed$/);
    const banner = await screen.findByTestId("memory-read-failures");
    expect(banner).toHaveTextContent(/Couldn't read Codex's memory:/);
    expect(banner).toHaveTextContent("~/.codex/memories");
    expect(within(banner).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(banner).getByRole("button", { name: "Open Activity" })).toBeInTheDocument();
  });

  test("while update memory runs the header counts the partitions it distils", async () => {
    stub([GLOBAL, COFFER]);
    vi.mocked(listUpkeepRuns).mockResolvedValue({
      runs: [
        { kind: "memory", name: "update", started_at: ago(1), done: 1, total: 5 },
        { kind: "memory", name: COFFER.uid, started_at: ago(0), done: null, total: null },
      ],
    });
    renderPage();
    expect(await screen.findByText("Distilling 2 of 5 partitions")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /updating…/i })).toBeDisabled();
    expect(await screen.findByText("Distilling…")).toBeInTheDocument();
  });

  // scenario (memory, revise-web-ui-ia): "the partitions table names each partition's sample, sources and distil state"
  test("partitions are a table with path, sample, sources and distil, and a count above it", async () => {
    stub([GLOBAL, COFFER, GONE]);
    renderPage();
    const section = await screen.findByTestId("memory-partitions");
    await within(section).findByRole("table");
    expect(within(section).getByText("3 partitions · 20 memories")).toBeInTheDocument();
    expect(within(section).getByText("Every project")).toBeInTheDocument();
    expect(within(section).getByText("~/work/coffer")).toBeInTheDocument();
    for (const header of ["Partition", "Path", "Sample memory", "Memories", "Sources", "Distil"]) {
      expect(within(section).getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    expect(within(section).getByText("Use Node 20 for frontend vitest")).toBeInTheDocument();
    expect(within(section).getAllByText("All agents")).toHaveLength(2);
    expect(within(section).getByText("Repository missing")).toBeInTheDocument();
    // Only the partition whose repository is gone can be deleted.
    expect(within(section).getAllByRole("button", { name: /^delete: /i })).toHaveLength(1);
    expect(
      within(section).getByRole("button", { name: /delete: old-prototype/i }),
    ).toBeInTheDocument();
  });

  test("with no partitions the first run lists what it found and carries one Update memory", async () => {
    stub([]);
    vi.mocked(agentsApi.list).mockResolvedValue({
      items: [
        {
          uid: "ag-cc",
          type: "claude_code",
          name: "claude-code",
          display_name: "Claude Code",
          config_dir: "/Users/dev/.claude",
        },
      ],
    } as unknown as Awaited<ReturnType<typeof agentsApi.list>>);
    vi.mocked(agentNativeMemoryApi.list).mockResolvedValue({
      items: [
        { project: "a", path: null, memory_dir: "/x/a", item_count: 30 },
        { project: "b", path: null, memory_dir: "/x/b", item_count: 12 },
      ],
    } as unknown as Awaited<ReturnType<typeof agentNativeMemoryApi.list>>);
    renderPage();
    expect(await screen.findByText("Nothing distilled yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(1);
    const found = await screen.findByTestId("memory-found");
    expect(await within(found).findByText("42 files in 2 projects")).toBeInTheDocument();
    expect(found).toHaveTextContent("~/.claude");
  });

  test("with no agent connected the first run offers to connect one", async () => {
    stub([]);
    renderPage();
    expect(await screen.findByText("No agent memory to read")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect an agent/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /update memory/i })).toBeNull();
  });

  test("no audit-log section — the Activity page holds the vault's whole trail", async () => {
    stub([COFFER]);
    renderPage();
    await screen.findByRole("table");
    expect(screen.queryByText(/audit log/i)).toBeNull();
  });
});
