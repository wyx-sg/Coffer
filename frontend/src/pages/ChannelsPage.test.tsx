// frontend/src/pages/ChannelsPage.test.tsx
// The Channels page as a list beside the open channel (spec channels "Manage
// channels from the Channels page and the CLI"): the list's groups, the first
// channel opened at `/channels`, the first-run page, the header each state
// puts a channel in (status word, banner, primary action), the tabs in the
// path, and the commands — reconnect (off and on again), send test, re-pair,
// delete. Only the network boundary is mocked: the api client, the channel
// status/pairing/notify requests, and the machine and agent registries.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { acceptance } from "@/test/acceptance";
import {
  AGENT,
  HERE,
  REGISTRY,
  THERE,
  makeChannel,
  makeStatus,
  renderChannelsPage,
  where,
} from "@/components/channel/channelTestKit";

const h = vi.hoisted(() => ({
  channels: [] as unknown[],
  statuses: new Map<string, unknown>(),
  client: {} as Record<string, ReturnType<typeof import("vitest").vi.fn>>,
}));

vi.mock("@/lib/api/client", () => ({ getApiClient: () => h.client }));
vi.mock("@/lib/api/channels", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/channels")>()),
  getChannelStatus: vi.fn(async (uid: string) => {
    const s = h.statuses.get(uid);
    if (s instanceof Error) throw s;
    return s;
  }),
  issuePairingCode: vi.fn(async () => ({
    code: "K7QM4XPT",
    expires_at: new Date(Date.now() + 58 * 60_000).toISOString(),
    pair_url: "",
  })),
  notifyChannel: vi.fn(async () => ({ sent: true })),
}));
vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: () => ({ data: { machines: REGISTRY } }),
  useThisMachineId: () => ({ machineId: HERE, isPending: false }),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [AGENT] }) }));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => ({ live: false }) }));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: () => ({ data: { scope: null, supports_scope: true } }),
  useUpdateResourceScope: () => ({ mutate: vi.fn(), isPending: false }),
}));

const { issuePairingCode, notifyChannel } = await import("@/lib/api/channels");

const TEAM = makeChannel();
const KICKED = makeChannel({ uid: "u-kick0001", name: "kicked-bot" });
const OPS = makeChannel({ uid: "u-ops00001", name: "ops-alerts", config: { runs_on: THERE } });
const REVIEW = makeChannel({ uid: "u-rev00001", name: "design-review" });

function serve(entries: [ResourceOut, ChannelStatus | Error][]) {
  h.channels = entries.map(([c]) => c);
  h.statuses = new Map(entries.map(([c, s]) => [c.uid, s]));
}

beforeEach(() => {
  h.client = {
    GET: vi.fn(async (path: string) =>
      path === "/resources"
        ? { data: { resources: h.channels }, error: undefined }
        : { data: undefined, error: undefined },
    ),
    POST: vi.fn(async () => ({ data: undefined, error: undefined })),
    PATCH: vi.fn(async () => ({ data: undefined, error: undefined })),
    PUT: vi.fn(async () => ({ data: undefined, error: undefined })),
    DELETE: vi.fn(async () => ({ data: undefined, error: undefined })),
  };
  serve([
    [TEAM, makeStatus(TEAM)],
    [KICKED, makeStatus(KICKED, { inbound: { websocket_state: "kicked", websocket_error: null } })],
    [OPS, makeStatus(OPS, { running: false, runs_here: false })],
    [REVIEW, makeStatus(REVIEW, { peer: null })],
  ]);
});
afterEach(() => vi.clearAllMocks());

const header = () => screen.getByTestId("channel-header");

describe("the list", () => {
  test("groups channels by state, each group with its count", async () => {
    renderChannelsPage(`/channels/${TEAM.uid}`);
    const attention = await screen.findByTestId("channel-group-attention");
    await waitFor(() => expect(within(attention).getAllByTestId("channel-row")).toHaveLength(2));
    expect(attention).toHaveTextContent("Needs attention2");
    expect(attention).toHaveTextContent("SeaTalk · kicked-bot");
    expect(attention).toHaveTextContent("Another process took the connection");
    expect(attention).toHaveTextContent("Not paired yet");
    expect(screen.getByTestId("channel-group-connected")).toHaveTextContent("SeaTalk · team-bot");
    expect(screen.getByTestId("channel-group-elsewhere")).toHaveTextContent("Runs on Mac mini");
  });

  test("/channels opens the first channel the list shows", async () => {
    renderChannelsPage("/channels");
    await waitFor(() => expect(where.url).toMatch(/^\/channels\/u-/));
    // Statuses may not be in yet when the redirect fires; any listed channel
    // is a fine first pick, and it is one the list holds.
    expect(h.channels.map((c) => `/channels/${(c as ResourceOut).uid}`)).toContain(where.url);
  });

  test("with no channel yet, the first-run page offers the platforms", async () => {
    serve([]);
    renderChannelsPage("/channels");
    expect(await screen.findByText("Talk to your agents from a chat app")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /telegram/i }));
    // A card opens Add channel straight at its Connect step.
    expect(await screen.findByRole("heading", { name: "Add Telegram channel" })).toBeVisible();
    expect(screen.getByLabelText(/bot token/i)).toBeInTheDocument();
  });
});

describe("the header says what state the channel is in", () => {
  const ghost = makeChannel({ uid: "u-ghost001", config: { runs_on: "machine-ghost" } });
  const tg = makeChannel({
    uid: "u-tg000001",
    name: "personal",
    config: { channel_type: "telegram", bot_token_ref: "channel/1/bot-token" },
  });
  const cases: [
    string,
    ResourceOut,
    ChannelStatus | Error,
    string,
    string | null,
    string | null,
  ][] = [
    ["connected", TEAM, makeStatus(TEAM), "Connected", null, "Send test"],
    [
      "connecting",
      TEAM,
      makeStatus(TEAM, { inbound: { websocket_state: "connecting", websocket_error: null } }),
      "Connecting",
      null,
      null,
    ],
    [
      "reconnecting",
      TEAM,
      makeStatus(TEAM, {
        inbound: { websocket_state: "connecting", websocket_error: "socket closed 1006" },
      }),
      "Reconnecting",
      "reconnecting",
      "Reconnect now",
    ],
    [
      "kicked",
      TEAM,
      makeStatus(TEAM, { inbound: { websocket_state: "kicked", websocket_error: null } }),
      "Kicked",
      "kicked",
      "Take it back",
    ],
    [
      "sdk missing",
      TEAM,
      makeStatus(TEAM, {
        inbound: { websocket_state: "sdk_missing", websocket_error: "put the SDK in vendor" },
      }),
      "Can't start",
      "sdkMissing",
      "Retry",
    ],
    [
      "connection error",
      TEAM,
      makeStatus(TEAM, { inbound: { websocket_state: "error", websocket_error: "auth failed" } }),
      "Can't connect",
      "connectFailed",
      "Replace secret",
    ],
    [
      "telegram stopped",
      tg,
      makeStatus(tg, { running: false }),
      "Stopped",
      "stopped",
      "Replace token",
    ],
    [
      "elsewhere",
      OPS,
      makeStatus(OPS, { runs_here: false }),
      "Runs on Mac mini",
      "elsewhere",
      "Run it here…",
    ],
    [
      "unknown machine",
      ghost,
      makeStatus(ghost, { runs_here: false }),
      "Runs nowhere",
      "unknownMachine",
      "Run it here",
    ],
    ["not paired", TEAM, makeStatus(TEAM, { peer: null }), "Not paired", "notPaired", null],
    [
      "status unavailable",
      TEAM,
      new Error("adapter did not answer"),
      "Unknown",
      "unavailable",
      "Retry",
    ],
  ];

  test.each(cases)("%s", async (_label, channel, status, word, banner, primary) => {
    serve([[channel, status]]);
    renderChannelsPage(`/channels/${channel.uid}`);
    await waitFor(() => expect(screen.getByTestId("channel-state-word")).toHaveTextContent(word));
    const banners = screen.queryAllByTestId("channel-banner").map((b) => b.dataset.state);
    expect(banners).toEqual(banner ? [banner] : []);
    const buttons = within(header())
      .getAllByRole("button")
      .map((b) => b.textContent)
      .filter((text) => text !== "");
    expect(buttons).toEqual(primary ? [primary] : []);
  });
});

acceptance(
  "channels/seatalk",
  "a missing sdk is handed to an agent from the channel page",
  async () => {
    // The download stays with the person (a link to SeaTalk's portal); the
    // rest is the daemon's hand-off, offered beside the header's Retry.
    serve([
      [
        TEAM,
        makeStatus(TEAM, {
          inbound: { websocket_state: "sdk_missing", websocket_error: "not found in /v" },
          handoff: { prompt: "Please put SeaTalk's WebSocket SDK where Coffer loads it from" },
        }),
      ],
    ]);
    renderChannelsPage(`/channels/${TEAM.uid}`);
    const banner = await screen.findByTestId("channel-banner");
    expect(banner.dataset.state).toBe("sdkMissing");
    expect(within(banner).getByRole("link", { name: "SeaTalk Open Platform" })).toHaveAttribute(
      "href",
      "https://open.seatalk.io/docs/WebSocket-Event-Callback",
    );
    expect(within(banner).getByRole("button", { name: /Copy prompt/ })).toBeInTheDocument();
    expect(within(banner).queryByText("not found in /v")).not.toBeInTheDocument();
    expect(within(header()).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  },
);

acceptance(
  "channels",
  "channel status reports runtime, pairing, and callback details",
  async () => {
    // The UI half: the page reads /channels/{uid}/status and reports the
    // adapter's state, the paired owner, and a SeaTalk channel's inbound state
    // — its websocket connection and the platform's own error behind it.
    serve([
      [
        TEAM,
        makeStatus(TEAM, {
          inbound: { websocket_state: "error", websocket_error: "register rejected: bad app id" },
          diagnostics: [{ code: "privacy_mode", message: "Privacy mode is on in BotFather." }],
        }),
      ],
    ]);
    renderChannelsPage(`/channels/${TEAM.uid}`);
    expect(await screen.findByText("register rejected: bad app id")).toBeInTheDocument();
    expect(screen.getByTestId("channel-state-word")).toHaveTextContent("Can't connect");
    expect(screen.getByTestId("channel-meta")).toHaveTextContent(
      "SeaTalk app 8231 · WebSocket · runs on this machine",
    );
    expect(screen.getByTestId("channel-owner")).toHaveTextContent("Alex Chen");
    expect(screen.getByTestId("channel-diagnostic")).toHaveTextContent("Privacy mode is on");
  },
);

acceptance(
  "channels",
  "a channel's detail opens on Overview and keeps Settings on its own tab",
  async () => {
    renderChannelsPage(`/channels/${TEAM.uid}/settings`);
    expect(await screen.findByTestId("channel-settings")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Overview" }));
    await waitFor(() => expect(where.url).toBe(`/channels/${TEAM.uid}`));
  },
);

acceptance("channels", "a channel links to its conversations instead of showing them", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}`);
  expect(await screen.findByTestId("channel-conversations-link")).toHaveAttribute(
    "href",
    `/conversations?channel=${TEAM.uid}`,
  );
  // Setup and connection status on Overview, settings on Settings — and no
  // tab, table or list of the channel's conversations.
  expect(screen.getByTestId("channel-state-word")).toBeInTheDocument();
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "Overview",
    "Settings",
  ]);
  expect(screen.queryByRole("tab", { name: /conversation|message|history/i })).toBeNull();
  expect(screen.queryByRole("region", { name: /conversations|messages/i })).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
});

test("reconnect turns the channel off and on again", async () => {
  serve([
    [KICKED, makeStatus(KICKED, { inbound: { websocket_state: "kicked", websocket_error: null } })],
  ]);
  renderChannelsPage(`/channels/${KICKED.uid}`);
  fireEvent.click(
    await within(await screen.findByTestId("channel-header")).findByRole("button", {
      name: /take it back/i,
    }),
  );
  await waitFor(() =>
    expect(h.client.POST.mock.calls.map((c) => c[0])).toEqual([
      "/resources/{uid}/disable",
      "/resources/{uid}/enable",
    ]),
  );
  expect(h.client.POST.mock.calls[0][1]).toEqual({ params: { path: { uid: KICKED.uid } } });
});

test("send test goes to the owner's direct chat with the editable message", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}`);
  fireEvent.click(
    await within(await screen.findByTestId("channel-header")).findByRole("button", {
      name: "Send test",
    }),
  );
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("Goes to Alex Chen's direct chat. No turn is started.");
  fireEvent.click(within(dialog).getByRole("button", { name: "Send" }));
  await waitFor(() =>
    expect(notifyChannel).toHaveBeenCalledWith(TEAM.uid, "Test message from Coffer"),
  );
});

test("re-pair asks first, then shows the new code", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}`);
  fireEvent.click(await screen.findByRole("button", { name: "Re-pair…" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("Alex Chen stops being the owner");
  expect(issuePairingCode).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole("button", { name: "Generate new code" }));
  expect(await screen.findByText("K7QM 4XPT")).toBeInTheDocument();
  expect(screen.getByText("Waiting for your message…")).toBeInTheDocument();
});

test("delete confirms, keeps conversations, and leaves the channel's address", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}`);
  fireEvent.click(await screen.findByRole("button", { name: /more actions/i }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Delete channel…" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("Conversations stay in Conversations");
  h.channels = h.channels.filter((c) => (c as ResourceOut).uid !== TEAM.uid);
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete channel" }));
  await waitFor(() =>
    expect(h.client.DELETE).toHaveBeenCalledWith("/resources/{uid}", {
      params: { path: { uid: TEAM.uid } },
    }),
  );
  await waitFor(() => expect(where.url).not.toBe(`/channels/${TEAM.uid}`));
});
