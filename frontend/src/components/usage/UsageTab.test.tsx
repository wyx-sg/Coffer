// src/components/usage/UsageTab.test.tsx — Model providers › Usage: metered API-key usage over a range, filters, breakdowns, first run, export.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { UsageSummary, UsageTotals } from "@/lib/api/usage";
import { acceptance } from "@/test/acceptance";
import { UsageTab } from "./UsageTab";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/activity/export", () => ({ saveFile: vi.fn() }));
const providerList = vi.hoisted(() => ({ current: [] as Array<Record<string, unknown>> }));
const agentList = vi.hoisted(() => ({ current: [] as Array<Record<string, unknown>> }));
vi.mock("@/lib/hooks/useProviders", () => ({
  useProviders: () => ({ data: providerList.current }),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({ data: agentList.current }),
}));

const { getApiClient } = await import("@/lib/api/client");
const { saveFile } = await import("@/lib/activity/export");

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
      connection_uid: "conn-1",
      connection_name: "Anthropic API",
      agent_types: ["claude_code"],
    }),
    row("m2", ACME, {
      model: "acme-coder-large",
      connection_uid: "conn-2",
      connection_name: "Acme AI gateway",
      agent_types: ["codex"],
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
      case "/usage/export.csv":
        return Promise.resolve({ data: "model,requests\r\nclaude-sonnet-4-5,3045\r\n" });
      case "/retention/policies":
        return Promise.resolve({
          data: { policies: [{ table_name: "mcp_invocations", retention_days: 10 }] },
        });
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

function renderTab(url = "/model-providers/usage") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[url]}>
            <UsageTab />
            <Where />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
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
      // No subscription quota, no refresh.
      expect(screen.queryByText(/quota/i)).toBeNull();
      expect(screen.queryByRole("button", { name: "Refresh" })).toBeNull();
      // Cost per day: one bar per local day of the range, named in its tooltip.
      const chart = await screen.findByRole("figure", { name: "Cost per day" });
      expect(within(chart).getAllByRole("img")).toHaveLength(7);
      expect(within(chart).getByRole("img", { name: "Thu 24 Sep · $25.81" })).toBeInTheDocument();

      const table = screen.getByRole("table");
      const rows = within(table).getAllByRole("row");
      expect(within(rows[1]).getByText("claude-sonnet-4-5")).toBeInTheDocument();
      expect(within(rows[1]).getByText("Anthropic API")).toBeInTheDocument();
      // In By model the second column is the agent.
      expect(within(table).getByRole("columnheader", { name: "Agent" })).toBeInTheDocument();
      expect(within(rows[1]).getByText("Claude Code")).toBeInTheDocument();
      // Nothing prices it: a dash, never $0.00, whose note says where a price is set.
      expect(
        within(rows[2]).getByLabelText(
          "No price is known for this model. Set one on its provider.",
        ),
      ).toHaveTextContent(/^—$/);
      expect(within(rows[2]).queryByText("$0.00")).not.toBeInTheDocument();
      expect(within(rows[3]).getByText("Total · 7 days")).toBeInTheDocument();
      expect(screen.queryByText(/Cost of priced models only/)).toBeNull();
    },
  );

  test("the range and the breakdown live in the URL and drive the summary", async () => {
    const { get } = install();
    renderTab();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Time range" }));
    fireEvent.click(await screen.findByRole("option", { name: "Last 30 days" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?range=30d"));
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({ range: "30d", group_by: "model" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "By agent" }));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent("?range=30d&by=agent"),
    );
    const table = await screen.findByRole("table");
    expect(await within(table).findByText("Codex")).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Agent" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "Via" })).toBeNull();
  });

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
    agentList.current = [{ uid: "a-codex", type: "codex", connection_uid: null }];
    const { get } = install();
    renderTab();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Agent" }));
    fireEvent.click(await screen.findByRole("option", { name: "Codex" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?agent=codex"));
    expect(screen.getByRole("button", { name: "Agent: Codex" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Provider" }));
    fireEvent.click(await screen.findByRole("option", { name: "Anthropic API" }));
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({
        range: "7d",
        group_by: "model",
        agent_type: "codex",
        connection_uid: "conn-1",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith("/usage/export.csv", {
        params: {
          query: { range: "7d", group_by: "model", agent_type: "codex", connection_uid: "conn-1" },
        },
        parseAs: "text",
      }),
    );
  });

  test("by day lists the newest day first with its top agent, the latest week before Show all", async () => {
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
    renderTab("/model-providers/usage?by=day");
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Top agent" })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent(/· today/);
    expect(within(rows[1]).getByText("Codex")).toBeInTheDocument();
    expect(within(table).getByText(/Showing 7 of 10 days/)).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Show all" }));
    // header + 10 days + total
    expect(within(table).getAllByRole("row")).toHaveLength(12);
  });

  test("a custom range is picked as dates and says how far back detail is kept", async () => {
    const { get } = install();
    renderTab("/model-providers/usage?range=custom&from=2026-09-01&to=2026-09-03");
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({
        range: "custom",
        from: "2026-09-01",
        to: "2026-09-03",
        group_by: "model",
      }),
    );
    const pill = screen.getByRole("button", { name: "Time range" });
    expect(pill).toHaveTextContent("Tue 1 Sep – Thu 3 Sep");
    fireEvent.click(pill);
    fireEvent.click(await screen.findByRole("option", { name: "Custom range…" }));
    const dialog = await screen.findByRole("dialog", { name: "Custom range" });
    expect(
      within(dialog).getByText(/^Before .+, only daily totals are kept\.$/),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("1 Sep 2026")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Custom range" })).toBeNull());
  });

  test("export writes the current range and grouping as CSV", async () => {
    const { get } = install();
    renderTab("/model-providers/usage?range=month&by=day");
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(saveFile).toHaveBeenCalled());
    expect(get).toHaveBeenCalledWith("/usage/export.csv", {
      params: { query: { range: "month", group_by: "day" } },
      parseAs: "text",
    });
    expect(vi.mocked(saveFile).mock.calls[0]).toEqual([
      "coffer-usage-month-day.csv",
      "text/csv",
      "model,requests\r\nclaude-sonnet-4-5,3045\r\n",
    ]);
  });
});

describe("first run", () => {
  test("no usage: the whole area says how usage starts and links to Providers", async () => {
    install({ empty: true });
    renderTab();
    expect(await screen.findByText("No API-key usage yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Requests an agent sends through an API-key provider show up here, with tokens and cost.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Providers" })).toHaveAttribute(
      "href",
      "/model-providers",
    );
    expect(screen.queryByRole("table")).toBeNull();
    // Nothing to narrow yet: no range, filters or export.
    expect(screen.queryByRole("button", { name: "Time range" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Export CSV" })).toBeNull();
  });

  test("an empty range after earlier usage only says the range is empty", async () => {
    install({ empty: true, usedBefore: true });
    renderTab();
    expect(await screen.findByText("No requests in this range")).toBeInTheDocument();
    expect(screen.queryByText("No API-key usage yet")).toBeNull();
    expect(screen.getByRole("button", { name: "Time range" })).toBeInTheDocument();
  });
});
