// ChannelCallbackCard: composed public callback URL display + reachability test.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ChannelCallbackCard } from "./ChannelCallbackCard";
import type { CallbackInfo } from "@/lib/api/channels";

vi.mock("@/lib/api/channels", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/channels")>()),
  testChannelCallback: vi.fn(),
}));

const { testChannelCallback } = await import("@/lib/api/channels");
const testMock = vi.mocked(testChannelCallback);

afterEach(() => vi.clearAllMocks());

const withUrl: CallbackInfo = {
  delivery: "webhook",
  port: 8787,
  path: "/seatalk/st",
  listener_running: true,
  public_base_url: "https://x.trycloudflare.com",
  public_callback_url: "https://x.trycloudflare.com/seatalk/st",
  tunnel_managed: false,
  tunnel_running: false,
  websocket_state: null,
  websocket_error: null,
};

const withoutUrl: CallbackInfo = {
  delivery: "webhook",
  port: 8787,
  path: "/seatalk/st",
  listener_running: true,
  public_base_url: null,
  public_callback_url: null,
  tunnel_managed: false,
  tunnel_running: false,
  websocket_state: null,
  websocket_error: null,
};

/**
 * Websocket delivery's wire shape: the webhook-only fields report their
 * absent/false values rather than pretending a listener or URL exists.
 */
const websocket: CallbackInfo = {
  delivery: "websocket",
  port: 8787,
  path: "/seatalk/st",
  listener_running: false,
  public_base_url: null,
  public_callback_url: null,
  tunnel_managed: false,
  tunnel_running: false,
  websocket_state: "connected",
  websocket_error: null,
};

test("shows the composed public callback URL with a copy button", () => {
  render(<ChannelCallbackCard name="st" callback={withUrl} />);
  expect(screen.getByText("https://x.trycloudflare.com/seatalk/st")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /copy|复制/i })).toBeInTheDocument();
});

test("without a base URL, shows no public URL / copy button", () => {
  render(<ChannelCallbackCard name="st" callback={withoutUrl} />);
  expect(screen.queryByText(/^https:\/\//)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /copy|复制/i })).not.toBeInTheDocument();
});

test("shows the managed-tunnel row only when a tunnel is managed", () => {
  const { rerender } = render(<ChannelCallbackCard name="st" callback={withUrl} />);
  expect(screen.queryByText(/^Tunnel$|^隧道$/)).not.toBeInTheDocument();
  rerender(
    <ChannelCallbackCard
      name="st"
      callback={{ ...withUrl, tunnel_managed: true, tunnel_running: true }}
    />,
  );
  expect(screen.getByText(/^Tunnel$|^隧道$/)).toBeInTheDocument();
});

describe("websocket delivery", () => {
  test("shows the connection state instead of the callback URL and its rows", () => {
    render(<ChannelCallbackCard name="st" callback={websocket} />);

    expect(screen.getByText(/^Connected$/)).toBeInTheDocument();
    // No URL to register, nothing to probe, no listener or tunnel to report.
    expect(screen.queryByText(/^https:\/\//)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /test reachability/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/^Listener$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Local listener$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Tunnel$/)).not.toBeInTheDocument();
  });

  test("a kicked connection reads as another process holding it, with the error text", () => {
    render(
      <ChannelCallbackCard
        name="st"
        callback={{
          ...websocket,
          websocket_state: "kicked",
          websocket_error: "kicked: registered elsewhere",
        }}
      />,
    );

    expect(screen.getByText(/another process holds this bot's connection/i)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("kicked: registered elsewhere");
  });

  test("a missing SDK reads as a missing SDK, not as a generic failure", () => {
    render(
      <ChannelCallbackCard name="st" callback={{ ...websocket, websocket_state: "sdk_missing" }} />,
    );

    expect(screen.getByText(/SDK not found/i)).toBeInTheDocument();
  });
});

describe("reachability test button", () => {
  test("calls the endpoint and renders the result detail", async () => {
    testMock.mockResolvedValue({ ok: true, detail: "reachable — verified" });
    render(<ChannelCallbackCard name="st" callback={withUrl} />);

    fireEvent.click(screen.getByRole("button", { name: /test|测试/i }));

    await waitFor(() => expect(testMock).toHaveBeenCalledWith("st"));
    expect(await screen.findByText(/reachable — verified/)).toBeInTheDocument();
  });
});
