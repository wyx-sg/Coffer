// src/pages/UsagePage.test.tsx — /usage: official quota per agent, metered API-key usage over a range, first run, export.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentQuota, UsageSummary, UsageTotals } from "@/lib/api/usage";
import { acceptance } from "@/test/acceptance";
import { UsagePage } from "./UsagePage";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
vi.mock("@/lib/activity/export", () => ({ saveFile: vi.fn() }));
// The providers an agent may run on: an active one that reaches an agent type
// puts that agent on an API key.
const providerList = vi.hoisted(() => ({ current: [] as Array<Record<string, unknown>> }));
vi.mock("@/lib/hooks/useProviders", () => ({
  useProviders: () => ({ data: providerList.current }),
}));

const { getApiClient } = await import("@/lib/api/client");
const { saveFile } = await import("@/lib/activity/export");

const HOUR = 3_600_000;
const inHours = (h: number) => new Date(Date.now() + h * HOUR).toISOString();

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
    row("m2", ACME, { model: "acme-coder-large", connection_name: "Acme AI gateway" }),
  ],
  ALL,
);
const BY_DAY = summary("day", [row("2026-09-24", SONNET, { day: "2026-09-24" })], ALL);
const BY_AGENT = summary("agent", [row("a1", ALL, { agent_type: "codex", agent_uid: "a1" })], ALL);
const EMPTY = (g: string) => summary(g, [], totals());

const win = (key: string, label: string, used: number | null, h: number, over = {}) => ({
  key,
  label,
  used_percent: used,
  window_minutes: 300,
  resets_at: inHours(h),
  as_of: new Date(Date.now() - 60_000).toISOString(),
  source: "codex_app_server",
  stale: false,
  ...over,
});

const QUOTA: AgentQuota[] = [
  {
    agent_type: "claude_code",
    plan: "max",
    has_value: true,
    last_observed_at: null,
    windows: [win("five_hour", "5-hour window", 42, 2), win("seven_day", "Weekly", 61, 60)],
  },
  {
    agent_type: "codex",
    plan: "plus",
    has_value: true,
    last_observed_at: null,
    windows: [
      win("primary", "Primary · 5 h", 91, 1),
      win("secondary", "Secondary · 7 days", 100, 130.5),
    ],
  },
];
const NO_QUOTA: AgentQuota[] = [
  { agent_type: "claude_code", plan: null, has_value: false, last_observed_at: null, windows: [] },
  { agent_type: "codex", plan: null, has_value: false, last_observed_at: null, windows: [] },
];

interface Setup {
  empty?: boolean;
  /** With `empty`: usage exists outside the range (the year the page asks about for first run). */
  usedBefore?: boolean;
  quota?: AgentQuota[] | "fail";
  refresh?: { refreshed: boolean; reason: string | null };
}

const FAIL = { data: undefined, error: { error: { code: "INTERNAL_ERROR", message: "boom" } } };

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
      case "/usage/quota":
        return Promise.resolve(
          setup.quota === "fail" ? FAIL : { data: { agents: setup.quota ?? QUOTA } },
        );
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
  const post = vi.fn(() =>
    Promise.resolve({
      data: {
        ...(setup.refresh ?? { refreshed: true, reason: null }),
        agents: Array.isArray(setup.quota) ? setup.quota : QUOTA,
      },
    }),
  );
  vi.mocked(getApiClient).mockReturnValue({ GET: get, POST: post } as unknown as ReturnType<
    typeof getApiClient
  >);
  return { get, post };
}

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.search}</output>;
}

function renderPage(url = "/usage") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[url]}>
            <UsagePage />
            <Where />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const quotaSection = () => screen.getByRole("region", { name: "Subscription quota" });
const usageSection = () => screen.getByRole("region", { name: "API-key providers" });
const summaryCalls = (get: ReturnType<typeof install>["get"]) =>
  get.mock.calls.filter(([p]) => p === "/usage/summary").map(([, init]) => init?.params?.query);

afterEach(() => {
  vi.clearAllMocks();
  providerList.current = [];
});

describe("subscription quota", () => {
  test("each window is a meter with its used share and reset; 90% warns, 100% is the limit", async () => {
    install();
    renderPage();
    const quota = quotaSection();
    expect(await within(quota).findByText("42% used")).toBeInTheDocument();
    expect(within(quota).getByText("Claude Max login")).toBeInTheDocument();
    // Codex also sent requests through an API-key provider in the range.
    expect(within(quota).getByText("ChatGPT Plus login · some requests")).toBeInTheDocument();
    expect(within(quota).getByText("via API key")).toBeInTheDocument();
    expect(within(quota).getByRole("progressbar", { name: "Weekly" })).toHaveAttribute(
      "aria-valuenow",
      "61",
    );
    expect(within(quota).getByText("91% used")).toHaveClass("text-warning");
    expect(within(quota).getByText("Limit reached")).toHaveClass("text-danger");
    expect(within(quota).getByText(/^Resets \d\d:\d\d · in 1 h/)).toBeInTheDocument();
    // The window reset in 130.5 h is at its limit, so it counts down too.
    expect(within(quota).getByText(/· in 5 d 10 h$/)).toBeInTheDocument();
    expect(within(quota).getAllByText(/^as of \d\d:\d\d$/)).toHaveLength(2);
    expect(within(quota).getAllByText("app-server")).toHaveLength(2);
  });

  acceptance("provider-switching", "no fresh value shows no number", async () => {
    install({
      quota: [
        { ...NO_QUOTA[0] },
        {
          ...QUOTA[1],
          windows: [win("primary", "Primary · 5 h", null, -1, { stale: true })],
        },
      ],
    });
    renderPage();
    const quota = quotaSection();
    expect(await within(quota).findByText("No quota reading yet")).toBeInTheDocument();
    expect(
      within(quota).getByText("Appears after your next Claude Code response."),
    ).toBeInTheDocument();
    expect(within(quota).getByText("Reset since last reading")).toBeInTheDocument();
    expect(within(quota).getByRole("progressbar", { name: "Primary · 5 h" })).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(within(quota).queryByText(/% used/)).toBeNull();
  });

  test("the statusline wrapper is described, never switched on by the page", async () => {
    install({ quota: NO_QUOTA });
    renderPage();
    const quota = quotaSection();
    expect(
      await within(quota).findByText("coffer usage statusline -- <your statusLine command>"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("switch")).toBeNull();
  });

  test("a Codex read that did not happen says why, with a retry", async () => {
    const { post } = install({
      quota: NO_QUOTA,
      refresh: { refreshed: false, reason: "read_failed" },
    });
    renderPage();
    await within(quotaSection()).findAllByText("No quota reading yet");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("Couldn't reach Codex's app-server")).toBeInTheDocument();
    expect(
      screen.getByText(/codex app-server exited before answering\. Last tried \d\d:\d\d\./),
    ).toBeInTheDocument();
    fireEvent.click(within(quotaSection()).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post).toHaveBeenCalledWith("/usage/quota/refresh");
    expect(within(quotaSection()).getByText("No reading")).toBeInTheDocument();
  });

  test("Claude Code's row re-reads its own quota", async () => {
    const { get, post } = install();
    renderPage();
    const quota = quotaSection();
    await within(quota).findByText("42% used");
    const before = get.mock.calls.filter(([p]) => p === "/usage/quota").length;
    fireEvent.click(within(quota).getByRole("button", { name: "Refresh Claude Code quota" }));
    await waitFor(() =>
      expect(get.mock.calls.filter(([p]) => p === "/usage/quota").length).toBe(before + 1),
    );
    expect(post).not.toHaveBeenCalled();
  });

  test("an agent on an API-key provider has no subscription quota and is metered", async () => {
    providerList.current = [
      {
        uid: "p1",
        name: "personal",
        title: null,
        base_url: "https://api.openai.com/v1",
        enabled: true,
        is_active: true,
        local_runtime: false,
        compatible_agents: ["codex"],
      },
    ];
    install({ quota: NO_QUOTA });
    renderPage();
    const quota = quotaSection();
    expect(await within(quota).findByText("API key · OpenAI")).toBeInTheDocument();
    expect(within(quota).getByText("No subscription quota")).toBeInTheDocument();
    expect(within(quota).getByText(/^Codex uses an API key from OpenAI here/)).toBeInTheDocument();
    expect(within(quota).getByText("Metered")).toBeInTheDocument();
    // Claude Code is still waiting for its first reading.
    expect(within(quota).getByText("Waiting")).toBeInTheDocument();
  });

  test("a failing quota read leaves the API-key section standing", async () => {
    install({ quota: "fail" });
    renderPage();
    expect(
      await within(quotaSection()).findByText("Couldn't load subscription quota."),
    ).toBeInTheDocument();
    expect((await within(usageSection()).findAllByText("$25.81")).length).toBeGreaterThan(0);
  });
});

describe("API-key usage", () => {
  acceptance(
    "provider-switching",
    "a model with no price reads as a dash, never zero",
    async () => {
      install();
      renderPage();
      const usage = usageSection();
      expect((await within(usage).findAllByText("$25.81")).length).toBeGreaterThan(0);
      expect(within(usage).getByText("Cost (estimated)")).toBeInTheDocument();
      expect(within(usage).getByText("3,092 requests · 47 unpriced")).toBeInTheDocument();
      expect(within(usage).getAllByText("6.00M").length).toBeGreaterThan(0);
      expect(within(usage).getAllByText("1.06M").length).toBeGreaterThan(0);
      // Cost per day: one bar per local day of the range, named in its tooltip.
      const chart = await within(usage).findByRole("figure", { name: "Cost per day" });
      expect(within(chart).getAllByRole("img")).toHaveLength(7);
      expect(within(chart).getByRole("img", { name: "Thu 24 Sep · $25.81" })).toBeInTheDocument();

      const table = within(usage).getByRole("table");
      const rows = within(table).getAllByRole("row");
      expect(within(rows[1]).getByText("claude-sonnet-4-5")).toBeInTheDocument();
      expect(within(rows[1]).getByText("Anthropic API")).toBeInTheDocument();
      expect(within(table).getByRole("columnheader", { name: "By" })).toBeInTheDocument();
      expect(within(rows[1]).getByLabelText("Claude Code")).toBeInTheDocument();
      // No bundled price and none set on the connection: a dash, never $0.00,
      // whose note says why and where a price is set.
      expect(
        within(rows[2]).getByLabelText(
          "No price for this model: Coffer ships Anthropic’s rates only. Set a price on its connection in Model providers.",
        ),
      ).toHaveTextContent(/^—$/);
      expect(within(rows[2]).queryByText("$0.00")).not.toBeInTheDocument();
      expect(
        within(rows[3]).getByText("Total · 7 days · cost of priced models"),
      ).toBeInTheDocument();
      expect(
        within(usage).getByRole("link", { name: "Edit prices in Model providers" }),
      ).toHaveAttribute("href", "/model-providers");
    },
  );

  test("the range and the breakdown live in the URL and drive the summary", async () => {
    const { get } = install();
    renderPage();
    const usage = usageSection();
    await within(usage).findByRole("table");
    fireEvent.click(within(usage).getByRole("button", { name: "30 days" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?range=30d"));
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({ range: "30d", group_by: "model" }),
    );
    fireEvent.mouseDown(within(usage).getByRole("tab", { name: "By agent" }));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent("?range=30d&by=agent"),
    );
    expect(await within(usage).findByText("Codex")).toBeInTheDocument();
    expect(within(usage).getByRole("columnheader", { name: "Agent" })).toBeInTheDocument();
    // Codex has a subscription login, so its API-key requests are tagged.
    expect(within(usage).getByRole("columnheader", { name: "Via" })).toBeInTheDocument();
    expect(within(usage).getByText("via API key")).toBeInTheDocument();
  });

  test("the Agent and Provider pills narrow the summary and the export", async () => {
    providerList.current = [
      {
        uid: "conn-1",
        name: "anthropic",
        title: "Anthropic API",
        base_url: "https://api.anthropic.com",
        enabled: true,
        is_active: false,
        local_runtime: false,
        compatible_agents: ["claude_code"],
      },
    ];
    const { get } = install();
    renderPage();
    const usage = usageSection();
    await within(usage).findByRole("table");
    fireEvent.click(within(usage).getByRole("button", { name: /^Agent:/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Codex" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?agent=codex"));
    fireEvent.click(within(usage).getByRole("button", { name: /^Provider:/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Anthropic API" }));
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({
        range: "7d",
        group_by: "model",
        agent_type: "codex",
        connection_uid: "conn-1",
      }),
    );
    fireEvent.click(within(usage).getByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Export CSV" }));
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
      if (path === "/usage/quota") return Promise.resolve({ data: { agents: QUOTA } });
      return Promise.resolve({ data: undefined });
    }) as typeof get);
    renderPage("/usage?by=day");
    const usage = usageSection();
    const table = await within(usage).findByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Top agent" })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent(/· today/);
    expect(within(rows[1]).getByText("Codex")).toBeInTheDocument();
    expect(within(table).getByText("3 earlier days ·")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Show all 10" }));
    // header + 10 days + total
    expect(within(table).getAllByRole("row")).toHaveLength(12);
  });

  test("a custom range opens a picker that says how far back detail is kept", async () => {
    const { get } = install();
    renderPage("/usage?range=custom&from=2026-09-01&to=2026-09-03");
    await waitFor(() =>
      expect(summaryCalls(get)).toContainEqual({
        range: "custom",
        from: "2026-09-01",
        to: "2026-09-03",
        group_by: "model",
      }),
    );
    const custom = within(usageSection()).getByRole("button", { name: "Tue 1 Sep – Thu 3 Sep" });
    expect(custom).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(custom);
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
    renderPage("/usage?range=month&by=day");
    await within(usageSection()).findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Export CSV" }));
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
  test("no usage and no quota: the page says how usage starts and links to Model providers", async () => {
    install({ empty: true, quota: NO_QUOTA });
    renderPage();
    const usage = usageSection();
    expect(await within(usage).findByText("No API-key usage yet")).toBeInTheDocument();
    expect(within(usage).getByRole("link", { name: "Open Model providers" })).toHaveAttribute(
      "href",
      "/model-providers",
    );
    expect(within(usage).queryByRole("table")).toBeNull();
    // Nothing to narrow yet: no range, filters or export.
    expect(within(usage).queryByRole("group", { name: "Period" })).toBeNull();
    expect(screen.queryByRole("button", { name: "More actions" })).toBeNull();
    // Claude Code has no reading yet; its row waits.
    expect(within(quotaSection()).getAllByText("Waiting")).toHaveLength(2);
  });

  test("an empty range after earlier usage only says the range is empty", async () => {
    install({ empty: true, usedBefore: true });
    renderPage();
    expect(
      await within(usageSection()).findByText("No requests in this range"),
    ).toBeInTheDocument();
    expect(screen.queryByText("No API-key usage yet")).toBeNull();
    expect(within(usageSection()).getByRole("group", { name: "Period" })).toBeInTheDocument();
  });
});
