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
  sync: vi.fn(),
}));
const api = await import("@/lib/api/memory");

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

  test("partitions are a table with path and memories, and a count above it", async () => {
    stub([GLOBAL, COFFER, GONE]);
    renderPage();
    const section = await screen.findByTestId("memory-partitions");
    await within(section).findByRole("table");
    expect(within(section).getByText("3 partitions · 20 memories")).toBeInTheDocument();
    expect(within(section).getByText("Every project")).toBeInTheDocument();
    expect(within(section).getByText("~/work/coffer")).toBeInTheDocument();
    // Only the partition whose repository is gone can be deleted.
    expect(within(section).getAllByRole("button", { name: /^delete: /i })).toHaveLength(1);
    expect(
      within(section).getByRole("button", { name: /delete: old-prototype/i }),
    ).toBeInTheDocument();
  });

  test("with no partitions the first-run state carries the one Update memory", async () => {
    stub([]);
    renderPage();
    expect(await screen.findByText("Nothing distilled yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(1);
    // The deliveries block still shows.
    expect(screen.getByTestId("memory-deliveries")).toBeInTheDocument();
  });

  test("no audit-log section — the Activity page holds the vault's whole trail", async () => {
    stub([COFFER]);
    renderPage();
    await screen.findByRole("table");
    expect(screen.queryByText(/audit log/i)).toBeNull();
  });
});
