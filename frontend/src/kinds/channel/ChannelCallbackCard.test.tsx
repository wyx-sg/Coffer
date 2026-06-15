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
  port: 8787,
  path: "/seatalk/st",
  listener_running: true,
  public_base_url: "https://x.trycloudflare.com",
  public_callback_url: "https://x.trycloudflare.com/seatalk/st",
  tunnel_managed: false,
  tunnel_running: false,
};

const withoutUrl: CallbackInfo = {
  port: 8787,
  path: "/seatalk/st",
  listener_running: true,
  public_base_url: null,
  public_callback_url: null,
  tunnel_managed: false,
  tunnel_running: false,
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

describe("reachability test button", () => {
  test("calls the endpoint and renders the result detail", async () => {
    testMock.mockResolvedValue({ ok: true, detail: "reachable — verified" });
    render(<ChannelCallbackCard name="st" callback={withUrl} />);

    fireEvent.click(screen.getByRole("button", { name: /test|测试/i }));

    await waitFor(() => expect(testMock).toHaveBeenCalledWith("st"));
    expect(await screen.findByText(/reachable — verified/)).toBeInTheDocument();
  });
});
