// src/components/usage/UsageTab.test.tsx — Model providers › Usage: metered API-key usage over a range, filters, first run.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import "@/i18n";
import { user } from "@/components/filters/testUser";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { UsageSummary, UsageTotals } from "@/lib/api/usage";
import { acceptance } from "@/test/acceptance";
import { UsageTab } from "./UsageTab";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
const providerList = vi.hoisted(() => ({ current: [] as Array<Record<string, unknown>> }));
const agentList = vi.hoisted(() => ({ current: [] as Array<Record<string, unknown>> }));
vi.mock("@/lib/hooks/useProviders", () => ({
  useProviders: () => ({ data: providerList.current }),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({ data: agentList.current }),
}));

const { getApiClient } = await import("@/lib/api/client");

function totals(over: Partial<UsageTotals> = {}): UsageTotals {
  return {
    requests: 0,
    input_tokens: 0,
    output_tokens: 0,
    reasoning_tokens: 0,
    cache_read_tokens: 0,
    cache_write_5m_tokens: 0,
    cache_write_1h_tokens: 0,
    web_search_requests: 0,
    estimated_cost_usd: 0,
    unpriced_requests: 0,
    unknown_usage_requests: 0,
    ...over,
  };
}

const SONNET = totals({
  requests: 3045,
  input_tokens: 5_820_000,
  output_tokens: 674_000,
  cache_read_tokens: 27_000_000,
  cache_write_5m_tokens: 1_000_000,
  cache_write_1h_tokens: 60_000,
  estimated_cost_usd: 25.81,
});
const ACME = totals({
  requests: 47,
  input_tokens: 180_000,
  output_tokens: 22_000,
  unpriced_requests: 47,
});

const row = (key: string, t: UsageTotals, extra: Partial<UsageSummary["rows"][number]> = {}) => ({
  key,
  model: null,
  connection_uid: null,
  connection_name: null,
  agent_type: null,
  agent_uid: null,
  day: null,
  agent_types: [],
  totals: t,
  ...extra,
});

function summary(group_by: string, rows: UsageSummary["rows"], tot: UsageTotals): UsageSummary {
  return {
    range: "7d",
    start: "2026-09-24",
    end: "2026-09-30",
    group_by,
    rows,
    totals: tot,
    cost_is_estimate: true,
    price_note: "Costs are estimates from the price version stored with each request.",
  };
}

const ALL = totals({
  ...SONNET,
  requests: 3092,
  input_tokens: 6_000_000,
  output_tokens: 696_000,
  unpriced_requests: 47,
});
const BY_MODEL = summary(
  "model",
  [
    row("m1", SONNET, {
      model: "claude-sonnet-4-5",
      connection_name: "Anthropic API",
      agent_types: ["claude_code"],
    }),
    row("m2", ACME, {
      model: "acme-coder-large",
      connection_uid: "conn-2",
      connection_name: "Acme AI gateway",
    }),
  ],
  ALL,
);
const BY_DAY = summary("day", [row("2026-09-24", SONNET, { day: "2026-09-24" })], ALL);
const BY_AGENT = summary("agent", [row("a1", ALL, { agent_type: "codex", agent_uid: "a1" })], ALL);
const EMPTY = (g: string) => summary(g, [], totals());

interface Setup {
  empty?: boolean;
  /** With `empty`: usage exists outside the range (the year the tab asks about for first run). */
  usedBefore?: boolean;
}

function install(setup: Setup = {}) {
  const get = vi.fn((path: string, init?: { params?: { query?: Record<string, string> } }) => {
    const q = init?.params?.query ?? {};
    switch (path) {
      case "/usage/summary": {
        const everQuery = q.range === "custom" && q.group_by === "agent";
        if (setup.empty && !(setup.usedBefore && everQuery)) {
          return Promise.resolve({ data: EMPTY(q.group_by) });
        }
        const byGroup = { model: BY_MODEL, day: BY_DAY, agent: BY_AGENT } as const;
        return Promise.resolve({ data: byGroup[q.group_by as keyof typeof byGroup] });
      }
      default:
        return Promise.resolve({ data: undefined });
    }
  });
  vi.mocked(getApiClient).mockReturnValue({ GET: get } as unknown as ReturnType<
    typeof getApiClient
  >);
  return { get };
}

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.search}</output>;
}

function renderTab(url = "/model-providers?tab=usage", onOpenProviders = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[url]}>
            <UsageTab onOpenProviders={onOpenProviders} />
            <Where />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onOpenProviders };
}

const summaryCalls = (get: ReturnType<typeof install>["get"]) =>
  get.mock.calls.filter(([p]) => p === "/usage/summary").map(([, init]) => init?.params?.query);

afterEach(() => {
  vi.clearAllMocks();
  providerList.current = [];
  agentList.current = [];
});

describe("API-key usage", () => {
  acceptance(
    "provider-switching",
    "a model with no price reads as a dash, never zero",
    async () => {
      install();
      renderTab();
      expect((await screen.findAllByText("$25.81")).length).toBeGreaterThan(0);
      expect(screen.getByText("Cost (estimated)")).toBeInTheDocument();
      expect(screen.getByText(/^3,092 requests/)).toBeInTheDocument();
      // The unpriced fact is one link in the Cost block, to the model on its provider.
      expect(screen.getByRole("link", { name: "1 model unpriced" })).toHaveAttribute(
        "href",
        "/model-providers?provider=conn-2&model=acme-coder-large",
      );
      expect(screen.getAllByText("6.00M").length).toBeGreaterThan(0);
      expect(screen.getAllByText("1.06M").length).toBeGreaterThan(0);
      // The price-source explanation sits behind the Cost label's "?".
      expect(screen.getByRole("button", { name: "About the cost estimate" })).toBeInTheDocument();
      // Cost per day: one bar per local day of the range, named in its tooltip.
      const chart = await screen.findByRole("figure", { name: "Cost per day" });
      expect(within(chart).getAllByRole("img")).toHaveLength(7);
      expect(within(chart).getByRole("img", { name: "Thu Sep 24 · $25.81" })).toBeInTheDocument();

      const table = screen.getByRole("table");
      const rows = within(table).getAllByRole("row");
      expect(within(rows[1]).getByText("claude-sonnet-4-5")).toBeInTheDocument();
      expect(within(rows[1]).getByText("Anthropic API")).toBeInTheDocument();
      expect(within(rows[1]).getByText("Claude Code")).toBeInTheDocument();
      // Nothing prices it: a bare dash with the reason on hover, never $0.00.
      const dash = within(rows[2]).getByLabelText(
        "No price is known for this model. Set one on its provider.",
      );
      expect(dash).toHaveTextContent(/^—$/);
      expect(within(rows[2]).queryByText("$0.00")).not.toBeInTheDocument();
      expect(within(rows[3]).getByText("Total · 7 days")).toBeInTheDocument();
      // In By model the second column is the agent; no footer repeats the price caveat.
      expect(within(table).getByRole("columnheader", { name: "Agent" })).toBeInTheDocument();
      expect(screen.queryByText(/Cost of priced models only/)).toBeNull();
      expect(screen.queryByRole("button", { name: "Edit prices" })).toBeNull();
    },
  );

  acceptance("provider-switching", "Coffer shows no subscription quota", async () => {
    const { get } = install();
    renderTab();
    await screen.findByRole("table");
    expect(screen.queryByText(/quota/i)).toBeNull();
    expect(get.mock.calls.some(([p]) => String(p).includes("quota"))).toBe(false);
    expect(screen.queryByRole("button", { name: "Refresh" })).toBeNull();
  });

  acceptance(
    "provider-switching",
    "the Usage tab keeps its range and filters in the address",
    async () => {
      const { get } = install();
      renderTab();
      await screen.findByRole("table");
      await user.click(screen.getByRole("button", { name: /Last 7 days/ }));
      await user.click(screen.getByRole("option", { name: "Last 30 days" }));
      await waitFor(() =>
        expect(screen.getByTestId("where")).toHaveTextContent("tab=usage&range=30d"),
      );
      await waitFor(() =>
        expect(summaryCalls(get)).toContainEqual({ range: "30d", group_by: "model" }),
      );
      // The breakdown is a segmented control, not tabs.
      expect(screen.queryByRole("tab")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "By agent" }));
      await waitFor(() =>
        expect(screen.getByTestId("where")).toHaveTextContent("tab=usage&range=30d&by=agent"),
      );
      expect(await screen.findByText("Codex")).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "Agent" })).toBeInTheDocument();
    },
  );

  test("the Agent and Provider pills narrow the summary and the export", async () => {
    providerList.current = [
      {
        uid: "conn-1",
        name: "anthropic",
        title: "Anthropic API",
        base_url: "https://api.anthropic.com",
        enabled: true,
        local_runtime: false,
        compatible_agents: ["claude_code"],
      },
    ];
    agentList.current = [{ uid: "a-codex", type: "codex" }];
    const { get } = install();
    renderTab();
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Agent" }));
    await user.click(await screen.findByRole("option", { name: "Codex" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("agent=codex"));
    await user.click(screen.getByRole("button", { name: "Provider" }));
    await user.click(await screen.findByRole("option", { name: "Anthropic API" }));
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({
        range: "7d",
        group_by: "model",
        agent_type: "codex",
        connection_uid: "conn-1",
      }),
    );
  });

  test("by day lists the newest day first with its top agent, seven days before Show all", async () => {
    const { get } = install();
    const days = Array.from({ length: 10 }, (_, i) => {
      const d = new Date();
      d.setDate(d.getDate() - 9 + i);
      const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      return row(day, totals({ requests: i + 1 }), { day, agent_types: ["codex", "claude_code"] });
    });
    const tenDays = summary("day", days, ALL);
    get.mockImplementation(((
      path: string,
      init?: { params?: { query?: Record<string, string> } },
    ) => {
      const q = init?.params?.query ?? {};
      if (path === "/usage/summary") {
        const byGroup = { model: BY_MODEL, day: tenDays, agent: BY_AGENT } as const;
        return Promise.resolve({ data: byGroup[q.group_by as keyof typeof byGroup] });
      }
      return Promise.resolve({ data: undefined });
    }) as typeof get);
    renderTab("/model-providers?tab=usage&by=day");
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Top agent" })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent(/· today/);
    expect(within(rows[1]).getByText("Codex")).toBeInTheDocument();
    expect(within(table).getByText("Showing 7 of 10")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Show all" }));
    // header + 10 days + total
    expect(within(table).getAllByRole("row")).toHaveLength(12);
  });

  test("a custom range is two days in the URL and reads on the pill", async () => {
    const { get } = install();
    renderTab("/model-providers?tab=usage&range=2026-09-01..2026-09-03");
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({
        range: "custom",
        from: "2026-09-01",
        to: "2026-09-03",
        group_by: "model",
      }),
    );
    expect(await screen.findByRole("button", { name: /Sep 1.* – Sep 3/ })).toBeInTheDocument();
  });
});

describe("first run", () => {
  acceptance(
    "provider-switching",
    "the Usage tab has nothing to show before any usage",
    async () => {
      install({ empty: true });
      const { onOpenProviders } = renderTab();
      expect(await screen.findByText("No API-key usage yet")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Requests an agent sends through an API-key provider show up here, with tokens and cost.",
        ),
      ).toBeInTheDocument();
      expect(screen.queryByRole("table")).toBeNull();
      expect(screen.queryByRole("button", { name: /Last 7 days/ })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Open Providers" }));
      expect(onOpenProviders).toHaveBeenCalled();
    },
  );

  test("an empty range after earlier usage only says the range is empty", async () => {
    install({ empty: true, usedBefore: true });
    renderTab();
    expect(await screen.findByText("No requests in this range")).toBeInTheDocument();
    expect(screen.queryByText("No API-key usage yet")).toBeNull();
    expect(screen.getByRole("button", { name: /Last 7 days/ })).toBeInTheDocument();
  });
});
