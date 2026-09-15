// frontend/src/components/channel/ChannelsTable.test.tsx
//
// The channels list (spec channels, FR-041). Each row carries the platform type,
// default agent, a live runtime-health badge (Running/Stopped), the reach
// control, a paired-owner cell and a delete action — the health and
// paired cells fed by the per-row /channels/{name}/status query, which we stub
// here. The health badge mirrors the MCP-server surface's
// ServerHealthCell, so this test asserts it reflects the adapter `running`
// state.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { ChannelsTable } from "./ChannelsTable";
import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";

vi.mock("@/lib/hooks/useChannels", () => ({
  useChannelStatus: vi.fn(),
  CHANNEL_KIND: "channel",
}));

// The state column is now ScopeControl, so every row reaches the scope /
// agents / enable hooks. `scope` rides the list payload, so useResourceScope
// stays switched off and returns nothing.
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "cc" }] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useDeleteResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const { useChannelStatus } = await import("@/lib/hooks/useChannels");
const useChannelStatusMock = vi.mocked(useChannelStatus);

function status(name: string, over: Partial<ChannelStatus> = {}): ChannelStatus {
  return {
    name,
    channel_type: "telegram",
    enabled: true,
    running: true,
    peer: null,
    callback: null,
    ...over,
  };
}

/** Route each row's status query to a fixture keyed by channel name. */
function stubStatuses(byName: Record<string, ChannelStatus | undefined>) {
  useChannelStatusMock.mockImplementation(
    (name: string) => ({ data: byName[name] }) as ReturnType<typeof useChannelStatus>,
  );
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function channel(name: string, agent = "builtin"): ResourceOut {
  return {
    name,
    kind: "channel",
    config: { channel_type: "telegram", default_agent: agent },
    enabled: true,
  } as unknown as ResourceOut;
}

describe("ChannelsTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders one row per channel with name and default agent", () => {
    stubStatuses({ tg: status("tg"), st: status("st") });
    render(<ChannelsTable items={[channel("tg", "claude_code"), channel("st")]} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByText("tg")).toBeInTheDocument();
    expect(screen.getByText("st")).toBeInTheDocument();
    expect(screen.getByText("claude_code")).toBeInTheDocument();
  });

  test("shows a live health badge reflecting the adapter running state", () => {
    // tg's adapter is live -> Running; st's is down -> Stopped.
    stubStatuses({
      tg: status("tg", { running: true }),
      st: status("st", { running: false }),
    });
    render(<ChannelsTable items={[channel("tg"), channel("st")]} />, { wrapper: wrap(null) });

    const badges = screen.getAllByTestId("channel-health-badge");
    expect(badges).toHaveLength(2);
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Stopped")).toBeInTheDocument();
  });

  test("shows the paired owner when the channel has a peer", () => {
    stubStatuses({
      tg: status("tg", {
        running: true,
        peer: {
          chat_id: "123",
          display_name: "Alice",
          paired_at: "2026-07-09T00:00:00Z",
          active_conversation_id: null,
        },
      }),
    });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
  });

  test("the state column is the reach control, not a static badge", () => {
    stubStatuses({ tg: status("tg") });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });

    const row = within(screen.getByText("tg").closest("tr") as HTMLElement);
    // ONE button, whose label states the channel's current reach.
    const reach = within(row.getByTestId("scope-control")).getByRole("button");
    expect(reach).toHaveTextContent(/^every agent$/i);
    // And unlike a badge it is the place reach is changed: it opens the panel
    // carrying the three states as choices.
    fireEvent.click(reach);
    expect(screen.getByRole("radio", { name: /^disabled$/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /every agent/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /only selected agents/i })).toBeInTheDocument();
  });

  test("every row offers a labelled delete, behind a confirmation", () => {
    stubStatuses({ tg: status("tg") });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });

    const row = within(screen.getByText("tg").closest("tr") as HTMLElement);
    // Labelled, not a bare icon — the same affordance the other tables show.
    const del = row.getByRole("button", { name: /delete channel: tg/i });
    expect(del).toHaveTextContent(/delete/i);

    fireEvent.click(del);
    expect(screen.getByRole("dialog")).toHaveTextContent(/delete channel/i);
  });

  test("selecting rows reveals the shared reach control and a bulk delete", () => {
    stubStatuses({ tg: status("tg"), st: status("st") });
    render(<ChannelsTable items={[channel("tg"), channel("st")]} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    // The same one-button control the rows carry, naming the action because a
    // mixed selection has no single reach to report.
    const bar = within(screen.getByTestId("bulk-reach-control"));
    expect(bar.getByRole("button")).toHaveTextContent(/set reach/i);
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });

  test("falls back to a placeholder health cell before the status loads", () => {
    stubStatuses({ tg: undefined });
    const { container } = render(<ChannelsTable items={[channel("tg")]} />, {
      wrapper: wrap(null),
    });
    expect(screen.queryByTestId("channel-health-badge")).not.toBeInTheDocument();
    // The em-dash placeholder stands in until the query resolves.
    expect(within(container).getByText("tg")).toBeInTheDocument();
  });
});
