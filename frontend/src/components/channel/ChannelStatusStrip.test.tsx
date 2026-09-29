// ChannelStatusStrip: the one line that says whether a channel is live and
// where. For SeaTalk that includes the websocket connection Coffer holds to
// the platform and the last error behind it, and nothing else (spec
// channels/seatalk "Report the websocket connection as the channel's inbound
// state") — no listener, port, URL or tunnel to show, no probe to run, and no
// paragraph explaining the transport.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ChannelStatusStrip } from "./ChannelStatusStrip";
import type { ChannelStatus, InboundInfo } from "@/lib/api/channels";

vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn(), useThisMachineId: vi.fn() }));
vi.mock("@/lib/hooks/useChannels", () => ({ useRebindChannel: vi.fn() }));

const { useMachines, useThisMachineId } = await import("@/lib/hooks/useMachines");
const { useRebindChannel } = await import("@/lib/hooks/useChannels");

const HERE = "machine-here";

beforeEach(() => {
  vi.mocked(useMachines).mockReturnValue({
    data: { machines: [{ machine_id: HERE, name: "Laptop", is_self: true }] },
  } as unknown as ReturnType<typeof useMachines>);
  vi.mocked(useThisMachineId).mockReturnValue({ machineId: HERE, isPending: false });
  vi.mocked(useRebindChannel).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useRebindChannel>);
});

function renderStrip(inbound: InboundInfo | null) {
  const status = {
    uid: "u-1",
    name: "st",
    channel_type: "seatalk",
    enabled: true,
    running: true,
    pending_pairing: false,
    peer: null,
    inbound,
    runs_on: HERE,
    runs_here: true,
  } as ChannelStatus;
  return render(
    <ChannelStatusStrip uid="u-1" name="st" config={{ runs_on: HERE }} status={status} />,
  );
}

describe("ChannelStatusStrip", () => {
  test("shows the connection state beside the adapter, and nothing a webhook would have", () => {
    renderStrip({ websocket_state: "connected", websocket_error: null });

    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("SeaTalk connection")).toBeInTheDocument();
    expect(screen.getByText(/^Connected$/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/^https?:\/\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/listener|tunnel|127\.0\.0\.1/i)).not.toBeInTheDocument();
    // The transport explanation that used to sit under the badge is gone.
    expect(screen.queryByText(/dials out to SeaTalk/i)).not.toBeInTheDocument();
  });

  test("a kicked connection reads as another process holding it, with the error verbatim", () => {
    renderStrip({ websocket_state: "kicked", websocket_error: "kicked: registered elsewhere" });

    expect(screen.getByText(/another process holds this bot's connection/i)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("kicked: registered elsewhere");
  });

  test("a missing SDK reads as a missing SDK, not as a generic failure", () => {
    renderStrip({ websocket_state: "sdk_missing", websocket_error: null });

    expect(screen.getByText(/SDK not found/i)).toBeInTheDocument();
  });

  test("before the first attempt the state is unknown rather than a guess", () => {
    renderStrip({ websocket_state: null, websocket_error: null });

    expect(screen.getByText(/^Unknown$/)).toBeInTheDocument();
  });

  test("a channel with no inbound state shows no connection badge", () => {
    renderStrip(null);

    expect(screen.queryByText("SeaTalk connection")).not.toBeInTheDocument();
  });
});
