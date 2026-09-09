// frontend/src/kinds/channel/ChannelsTable.test.tsx
//
// The channels list (spec 009, FR-041). Each row carries the platform type,
// default agent, a live runtime-health badge (Running/Stopped), enabled state,
// and a paired-owner cell — all fed by the per-row /channels/{name}/status
// query, which we stub here. The health badge mirrors the MCP-server surface's
// ServerHealthCell, so this test asserts it reflects the adapter `running`
// state.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { ChannelsTable } from "./ChannelsTable";
import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/components/kindRegistry";

vi.mock("@/lib/hooks/useChannels", () => ({
  useChannelStatus: vi.fn(),
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
