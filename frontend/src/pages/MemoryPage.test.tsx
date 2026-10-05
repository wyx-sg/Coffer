// frontend/src/pages/MemoryPage.test.tsx
//
// The Memory overview (spec memory "Show a partition's memories read-only"): the
// partitions table, untitled and searchable, or the first-run state while there
// are none. Only the api module is mocked;
// the real hooks run over a real QueryClient.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { COFFER, GLOBAL, GONE } from "@/components/memory/memoryTestData";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { acceptance } from "@/test/acceptance";
import { pathText } from "@/test/truncatedPath";
import { MemoryPage } from "./MemoryPage";

vi.mock("@/lib/api/memory", () => ({
  listPartitions: vi.fn(),
  getReading: vi.fn(),
  sync: vi.fn(),
  getTidyHandoff: vi.fn(),
}));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => ({ live: false }) }));
vi.mock("@/lib/api/upkeep", () => ({ listUpkeepRuns: vi.fn() }));
vi.mock("@/lib/api/internalEngine", () => ({ internalEngineApi: { get: vi.fn() } }));
vi.mock("@/lib/api/agents", () => ({ agentsApi: { list: vi.fn() } }));
vi.mock("@/lib/api/agentNativeMemory", () => ({ agentNativeMemoryApi: { list: vi.fn() } }));
const api = await import("@/lib/api/memory");
const { listUpkeepRuns } = await import("@/lib/api/upkeep");
const { internalEngineApi } = await import("@/lib/api/internalEngine");
const { agentsApi } = await import("@/lib/api/agents");
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const { agentNativeMemoryApi } = await import("@/lib/api/agentNativeMemory");

const MINUTE = 60_000;
const ago = (minutes: number) => new Date(Date.now() - minutes * MINUTE).toISOString();

function stub(partitions: PartitionOut[]) {
  vi.mocked(api.listPartitions).mockResolvedValue({ partitions });
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
    vi.mocked(api.getReading).mockResolvedValue({ read_at: ago(14), failures: [] });
    vi.mocked(listUpkeepRuns).mockResolvedValue({ runs: [] });
    vi.mocked(internalEngineApi.get).mockResolvedValue({
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
    vi.mocked(agentProvidersApi.list).mockResolvedValue({ agents: [] });
    vi.mocked(api.getTidyHandoff).mockResolvedValue({ prompt: "Tidy every partition." });
  });

  test("says what memory is, with one Update memory button", async () => {
    stub([GLOBAL, COFFER]);
    renderPage();
    await screen.findByRole("table");
    expect(screen.getByText(/kept as memories for each repository\./i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^sync$/i })).toBeNull();
  });

  test("the header carries the Experimental tag and Update memory as the one primary button", async () => {
    stub([GLOBAL, COFFER]);
    renderPage();
    await screen.findByRole("table");
    expect(screen.getByText("Experimental")).toBeInTheDocument();
    // The primary kind is the filled accent button; the outline kind is not.
    expect(screen.getByRole("button", { name: /update memory/i }).className).toMatch(/bg-accent/);
  });

  test("idle, the header shows no status line, with the schedule behind Update memory's arrow", async () => {
    stub([COFFER]);
    renderPage();
    const arrow = await screen.findByTestId("memory-automatic");
    expect(arrow).toHaveAccessibleName("Read memory automatically");
    expect(screen.queryByTestId("memory-status")).toBeNull();
    expect(screen.queryByText(/Reads automatically/)).toBeNull();
  });

  test("a read that left an agent unread says so in a banner", async () => {
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
    const banner = await screen.findByTestId("memory-read-failures");
    expect(banner).toHaveTextContent(/Couldn't read Codex's memory:/);
    expect(banner).toHaveTextContent("~/.codex/memories");
    expect(within(banner).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    // Hand off to <Agent> hands the fix to an agent; Open Activity is gone.
    expect(
      within(banner).getByRole("button", { name: /copy prompt|ask an agent/i }),
    ).toBeInTheDocument();
    expect(within(banner).queryByRole("button", { name: "Open Activity" })).toBeNull();
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

  test('a run with no done/total yet reads "Reading agents\' memory…"', async () => {
    stub([GLOBAL, COFFER]);
    vi.mocked(listUpkeepRuns).mockResolvedValue({
      runs: [{ kind: "memory", name: "update", started_at: ago(0), done: null, total: null }],
    });
    renderPage();
    expect(await screen.findByText("Reading agents’ memory…")).toBeInTheDocument();
  });

  test("partitions are an untitled table with path, sources and distil, and no count", async () => {
    stub([GLOBAL, COFFER, GONE]);
    renderPage();
    const section = await screen.findByTestId("memory-partitions");
    await within(section).findByRole("table");
    expect(within(section).queryByText("3 partitions · 20 memories")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Partitions" })).toBeNull();
    expect(within(section).getByText("Every project")).toBeInTheDocument();
    expect(within(section).getByText(pathText("~/work/coffer"))).toBeInTheDocument();
    for (const header of ["Partition", "Path", "Memories", "Sources", "Distilled"]) {
      expect(within(section).getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    expect(within(section).queryByRole("columnheader", { name: "Sample memory" })).toBeNull();
    expect(within(section).getAllByText("All agents")).toHaveLength(2);
    expect(within(section).getByText("Repository missing")).toBeInTheDocument();
    // Healthy states are a grey dot; only the missing repository is coloured.
    const dotOf = (word: RegExp) =>
      within(section).getAllByText(word)[0].querySelector("[data-tone]")?.getAttribute("data-tone");
    expect(dotOf(/^Distilled /)).toBe("off");
    expect(dotOf(/^Repository missing$/)).toBe("warn");
    // Only the partition whose repository is gone can be deleted.
    expect(within(section).getAllByRole("button", { name: /^delete: /i })).toHaveLength(1);
    expect(
      within(section).getByRole("button", { name: /delete: old-prototype/i }),
    ).toBeInTheDocument();
  });

  acceptance(
    "memory",
    "the partitions table names each partition's sources and distil state",
    async () => {
      const pending: PartitionOut = {
        ...COFFER,
        uid: "mp-new",
        name: "new-repo",
        repository_path: "/Users/dev/work/new-repo",
        repository_key: "path:/Users/dev/work/new-repo",
        note_count: 0,
        distilled_at: null,
        sources: [],
        waiting_entries: 4,
        waiting_agents: ["codex"],
      };
      stub([GLOBAL, pending, GONE]);
      renderPage();
      const section = await screen.findByTestId("memory-partitions");
      const [, first, second, third] = within(
        await within(section).findByRole("table"),
      ).getAllByRole("row");
      expect(first).toHaveTextContent("All agents");
      expect(first).toHaveTextContent(/Distilled /);
      expect(second).toHaveTextContent("new-repo");
      expect(second).toHaveTextContent("Never");
      expect(third).toHaveTextContent("Repository missing");
      expect(within(third).getByRole("button", { name: /^delete: /i })).toBeInTheDocument();
    },
  );

  acceptance(
    "web-ui",
    "the Memory page shows the partitions with a search and no delivery block",
    async () => {
      stub([GLOBAL, COFFER, GONE]);
      renderPage();
      const section = await screen.findByTestId("memory-partitions");
      const table = await within(section).findByRole("table");
      const search = within(section).getByPlaceholderText("Search partitions");
      fireEvent.change(search, { target: { value: "work/coffer" } });
      const rows = within(table).getAllByRole("row").slice(1);
      expect(rows).toHaveLength(1);
      expect(rows[0]).toHaveTextContent("coffer");
      expect(screen.queryByTestId("memory-deliveries")).toBeNull();
      expect(screen.queryByRole("heading", { name: "Partitions" })).toBeNull();
    },
  );

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
    expect(screen.getByRole("button", { name: "Open Agents →" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /update memory/i })).toBeNull();
  });

  test("no audit-log section — the Activity page holds the vault's whole trail", async () => {
    stub([COFFER]);
    renderPage();
    await screen.findByRole("table");
    expect(screen.queryByText(/audit log/i)).toBeNull();
  });
});
