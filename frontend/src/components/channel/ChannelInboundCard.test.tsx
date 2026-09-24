// ChannelInboundCard: a SeaTalk channel's inbound state — the websocket
// connection Coffer holds to the platform and the last error behind it, and
// nothing else (spec channels/seatalk "Report the websocket connection as the
// channel's inbound state"). There is no listener, port, URL or tunnel to show,
// and no probe to run.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { ChannelInboundCard } from "./ChannelInboundCard";
import type { InboundInfo } from "@/lib/api/channels";

const connected: InboundInfo = { websocket_state: "connected", websocket_error: null };

describe("ChannelInboundCard", () => {
  test("shows the connection state and nothing a webhook would have", () => {
    render(<ChannelInboundCard inbound={connected} />);

    expect(screen.getByText(/^Connected$/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/^https?:\/\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/listener|tunnel|127\.0\.0\.1/i)).not.toBeInTheDocument();
  });

  test("a kicked connection reads as another process holding it, with the error verbatim", () => {
    render(
      <ChannelInboundCard
        inbound={{ websocket_state: "kicked", websocket_error: "kicked: registered elsewhere" }}
      />,
    );

    expect(screen.getByText(/another process holds this bot's connection/i)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("kicked: registered elsewhere");
  });

  test("a missing SDK reads as a missing SDK, not as a generic failure", () => {
    render(
      <ChannelInboundCard inbound={{ websocket_state: "sdk_missing", websocket_error: null }} />,
    );

    expect(screen.getByText(/SDK not found/i)).toBeInTheDocument();
  });

  test("before the first attempt the state is unknown rather than a guess", () => {
    render(<ChannelInboundCard inbound={{ websocket_state: null, websocket_error: null }} />);

    expect(screen.getByText(/^Unknown$/)).toBeInTheDocument();
  });
});
