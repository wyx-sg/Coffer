// frontend/src/pages/ChannelsPage.test.tsx
// The Channels page as a list beside the open channel (spec channels "Manage
// channels from the Channels page"): the list's groups, the first
// channel opened at `/channels`, the first-run page, the header each state
// puts a channel in (status word, banner, primary action), the tabs in the
// path, and the commands — reconnect (a restart request), send test, re-pair,
// delete. Only the network boundary is mocked: the api client, the channel
// status/pairing/notify requests, and the agent registry.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { acceptance } from "@/test/acceptance";
import { AGENT, makeChannel, makeStatus, renderChannelsPage, where } from "@/test/channelKit";

const h = vi.hoisted(() => ({
  channels: [] as unknown[],
  statuses: new Map<string, unknown>(),
  client: {} as Record<string, ReturnType<typeof import("vitest").vi.fn>>,
}));

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => h.client,
}));
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
  cancelPairingCode: vi.fn(async () => undefined),
  removeChannelPerson: vi.fn(async () => undefined),
  getChannelPersonAvatar: vi.fn(async (_uid: string, senderId: string) =>
    senderId === "ann" ? "data:image/png;base64,iVBORw0KGgo=" : null,
  ),
  notifyChannel: vi.fn(async () => ({ sent: true })),
  restartChannel: vi.fn(async () => ({ running: true })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({ data: [AGENT] }),
  useAgent: () => ({ data: undefined }),
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => ({ live: false }) }));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: () => ({ data: { scope: null, supports_scope: true } }),
  useUpdateResourceScope: () => ({ mutate: vi.fn(), isPending: false }),
}));

const { cancelPairingCode, issuePairingCode, notifyChannel, removeChannelPerson, restartChannel } =
  await import("@/lib/api/channels");

const TEAM = makeChannel();
const KICKED = makeChannel({ uid: "u-kick0001", name: "kicked-bot" });
const OPS = makeChannel({ uid: "u-ops00001", name: "ops-alerts", enabled: false });
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
    [OPS, makeStatus(OPS, { running: false })],
    [REVIEW, makeStatus(REVIEW, { people: [] })],
  ]);
});
afterEach(() => vi.clearAllMocks());

const header = () => screen.getByTestId("channel-header");

describe("the list", () => {
  test("groups channels by state, headings carry no count", async () => {
    renderChannelsPage(`/channels/${TEAM.uid}`);
    const attention = await screen.findByTestId("channel-group-attention");
    await waitFor(() => expect(within(attention).getAllByTestId("channel-row")).toHaveLength(2));
    expect(attention).toHaveTextContent(/^Needs attention(?!\d)/);
    expect(attention).toHaveTextContent("SeaTalk · kicked-bot");
    expect(attention).toHaveTextContent("Another process took the connection");
    expect(attention).toHaveTextContent("Not paired yet");
    expect(screen.getByTestId("channel-group-connected")).toHaveTextContent("SeaTalk · team-bot");
    expect(screen.getByTestId("channel-group-off")).toHaveTextContent("SeaTalk · ops-alerts");
  });

  test("the list is folded by dragging its divider, not by a button", async () => {
    renderChannelsPage(`/channels/${TEAM.uid}`);
    expect(await screen.findByRole("separator")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /hide list/i })).toBeNull();
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
    expect(await screen.findByRole("heading", { name: "Add a Telegram channel" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: /bot token/i })).toBeInTheDocument();
  });
});

describe("the header says what state the channel is in", () => {
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
    ["connected", TEAM, makeStatus(TEAM), "Connected", null, null],
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
      "app refused by seatalk",
      TEAM,
      makeStatus(TEAM, {
        inbound: { websocket_state: "rejected", websocket_error: "RegisterError: code=1" },
      }),
      "Token rejected",
      "connectFailed",
      "Replace secret",
    ],
    [
      "network error",
      TEAM,
      makeStatus(TEAM, {
        inbound: { websocket_state: "error", websocket_error: "gaierror: [Errno 8] not known" },
      }),
      "Network problem",
      "unreachable",
      "Reconnect now",
    ],
    [
      "telegram stopped",
      tg,
      makeStatus(tg, { running: false }),
      "Token rejected",
      "stopped",
      "Replace token",
    ],
    [
      "secret waiting for approval",
      TEAM,
      makeStatus(TEAM, {
        running: false,
        secret_approval: { state: "pending", secret_ref: "channel/team/app-secret" },
      }),
      "Waiting for approval",
      "waitingApproval",
      "Open Secrets",
    ],
    [
      "secret refused",
      TEAM,
      makeStatus(TEAM, {
        running: false,
        secret_approval: { state: "refused", secret_ref: "channel/team/app-secret" },
      }),
      "Secret refused",
      "approvalRefused",
      "Ask again",
    ],
    ["off", OPS, makeStatus(OPS, { running: false }), "Off", "quiet:off", "Turn on"],
    ["not paired", TEAM, makeStatus(TEAM, { people: [] }), "Not paired", "notPaired", null],
    [
      "status unavailable",
      TEAM,
      new Error("adapter did not answer"),
      "Status unknown",
      "unavailable",
      "Retry",
    ],
  ];

  test.each(cases)("%s", async (_label, channel, status, word, banner, primary) => {
    serve([[channel, status]]);
    renderChannelsPage(`/channels/${channel.uid}`);
    await waitFor(() => expect(screen.getByTestId("channel-state-word")).toHaveTextContent(word));
    // A problem is a banner holding its fix; off is a quiet box.
    const quiet = banner?.startsWith("quiet:") ?? false;
    const testId = quiet ? "channel-quiet" : "channel-banner";
    const found = screen.queryAllByTestId(testId).map((b) => b.dataset.state);
    expect(found).toEqual(banner ? [banner.replace("quiet:", "")] : []);
    // The header never changes with the state: Send test, then the ⋯ menu.
    const buttons = within(header())
      .getAllByRole("button")
      .map((b) => b.textContent)
      .filter((text) => text !== "");
    expect(buttons).toEqual(["Send test"]);
    if (primary && !banner) throw new Error("a fix needs a banner");
    if (primary) {
      const box = screen.getByTestId(testId);
      expect(within(box).getByRole("button", { name: primary })).toBeInTheDocument();
    }
    // Replacing the secret is offered only where the secret is the problem.
    if (primary !== "Replace secret" && primary !== "Replace token" && !quiet && banner) {
      const box = screen.getByTestId(testId);
      expect(within(box).queryByRole("button", { name: /Replace/ })).toBeNull();
    }
  });
});

acceptance(
  "channels/seatalk",
  "a missing sdk is handed to an agent from the channel page",
  async () => {
    // The download stays with the person (a link to SeaTalk's portal); the
    // rest is the daemon's hand-off, offered beside the banner's Retry.
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
    expect(within(banner).getByRole("button", { name: "Retry" })).toBeInTheDocument();
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
          inbound: {
            websocket_state: "rejected",
            websocket_error: "register rejected: bad app id",
          },
          diagnostics: [{ code: "privacy_mode", message: "Privacy mode is on in BotFather." }],
        }),
      ],
    ]);
    renderChannelsPage(`/channels/${TEAM.uid}`);
    expect(await screen.findByText("register rejected: bad app id")).toBeInTheDocument();
    expect(screen.getByTestId("channel-state-word")).toHaveTextContent("Token rejected");
    expect(screen.getByTestId("channel-meta")).toHaveTextContent("SeaTalk app 8231 · WebSocket");
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
    `/conversations?source=${TEAM.uid}`,
  );
  expect(screen.getByTestId("channel-state-word")).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
});

acceptance(
  "channels",
  "a channel's Overview links to its conversations instead of listing them",
  async () => {
    renderChannelsPage(`/channels/${TEAM.uid}`);
    expect(await screen.findByTestId("channel-conversations-link")).toHaveAttribute(
      "href",
      `/conversations?source=${TEAM.uid}`,
    );
    // Setup and connection status on Overview, settings on Settings — and no
    // tab, table or list of the channel's conversations.
    expect(screen.getByTestId("channel-state-word")).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Settings",
    ]);
    expect(screen.queryByRole("tab", { name: /conversation|message|history/i })).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    // One link, and nothing listed in place.
    expect(screen.getByTestId("channel-conversations-link")).toHaveTextContent(
      "Conversations from this channel",
    );
    expect(screen.queryByTestId("channel-recent-conversations")).toBeNull();
  },
);

test("the Overview has no Commands section: the list lives in the reference docs", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}`);
  await screen.findByTestId("channel-overview");
  expect(screen.queryByTestId("channel-commands")).toBeNull();
});

test("reconnect asks the daemon to restart the channel's adapter", async () => {
  serve([
    [KICKED, makeStatus(KICKED, { inbound: { websocket_state: "kicked", websocket_error: null } })],
  ]);
  renderChannelsPage(`/channels/${KICKED.uid}`);
  fireEvent.click(
    await within(await screen.findByTestId("channel-banner")).findByRole("button", {
      name: /take it back/i,
    }),
  );
  await waitFor(() => expect(restartChannel).toHaveBeenCalledWith(KICKED.uid));
  // One request, addressed to the channel; no off-and-on through enable/disable.
  expect(h.client.POST).not.toHaveBeenCalled();
});

test("Ask again on a refused secret asks again for each refused request of this channel", async () => {
  serve([
    [
      TEAM,
      makeStatus(TEAM, {
        running: false,
        secret_approval: { state: "refused", secret_ref: "channel/team/app-secret" },
      }),
    ],
  ]);
  h.client.GET.mockImplementation(async (path: string) =>
    path === "/resources"
      ? { data: { resources: h.channels }, error: undefined }
      : path === "/secrets/approvals"
        ? { data: { approvals: [{ id: "apr-1" }] }, error: undefined }
        : { data: undefined, error: undefined },
  );
  h.client.POST.mockImplementation(async () => ({ data: { approvals: [] }, error: undefined }));
  renderChannelsPage(`/channels/${TEAM.uid}`);
  fireEvent.click(
    await within(await screen.findByTestId("channel-banner")).findByRole("button", {
      name: /ask again/i,
    }),
  );
  await waitFor(() =>
    expect(h.client.POST).toHaveBeenCalledWith("/secrets/approvals/{approval_id}/ask-again", {
      params: { path: { approval_id: "apr-1" } },
    }),
  );
  expect(h.client.GET).toHaveBeenCalledWith("/secrets/approvals", {
    params: { query: { status: "rejected", destination_uid: TEAM.uid } },
  });
});

test("the ⋯ menu holds only Reconnect: Send test and the Settings actions are not repeated", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}`);
  fireEvent.click(await screen.findByRole("button", { name: /more actions/i }));
  const items = await screen.findAllByRole("menuitem");
  expect(items.map((i) => i.textContent)).toEqual(["Reconnect"]);
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

test("there is no re-pair: an owner row offers Remove only, and a new owner is added instead", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}`);
  const owner = await screen.findByTestId("channel-owner");
  expect(within(owner).getByRole("button", { name: "Remove" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /re-pair/i })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add owner" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  // The code is for a NEW person: it names nobody to replace.
  await waitFor(() => expect(issuePairingCode).toHaveBeenCalledWith(TEAM.uid, undefined));
});

const ANN = {
  sender_id: "ann",
  display_name: "Ann Lee",
  chat_id: "c-2",
  paired_at: "2026-09-13T08:00:00Z",
  active_conversation_id: null,
};

describe("several owners", () => {
  const two = () => {
    const base = makeStatus(TEAM);
    serve([[TEAM, { ...base, people: [...base.people, ANN] }]]);
  };

  test("lists every paired owner and says strangers get silence", async () => {
    two();
    renderChannelsPage(`/channels/${TEAM.uid}`);
    const rows = await screen.findAllByTestId("channel-owner");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Alex Chen");
    expect(rows[1]).toHaveTextContent("Ann Lee");
    expect(screen.queryByText("2 owners")).not.toBeInTheDocument();
    // The strangers line lives in the heading's help tip, not inline.
    expect(screen.queryByText(/strangers get silence/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("channel-pairing-code")).not.toBeInTheDocument();
  });

  acceptance(
    "channels",
    "an owner row shows the person's platform picture or their initials",
    async () => {
      two();
      renderChannelsPage(`/channels/${TEAM.uid}`);
      const rows = await screen.findAllByTestId("channel-owner");
      // Ann has a picture on the platform; Alex has none and keeps initials.
      expect(await within(rows[1]).findByTestId("channel-owner-avatar")).toHaveAttribute(
        "src",
        "data:image/png;base64,iVBORw0KGgo=",
      );
      expect(within(rows[0]).queryByTestId("channel-owner-avatar")).not.toBeInTheDocument();
      expect(rows[0]).toHaveTextContent("AC");
      // The line under the name says who they are and since when, nothing more.
      expect(rows[0]).toHaveTextContent(/Owner · paired \w+ \d+/);
      expect(rows[0]).not.toHaveTextContent("direct chat");
    },
  );

  test("Add owner opens the dialog, and Esc withdraws the code", async () => {
    renderChannelsPage(`/channels/${TEAM.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: "Add owner" }));
    expect(await screen.findByText("K7QM 4XPT")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("Add an owner");
    // An add carries no target: whoever sends the code joins the others.
    expect(issuePairingCode).toHaveBeenCalledWith(TEAM.uid, undefined);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(cancelPairingCode).toHaveBeenCalledWith(TEAM.uid));
    await waitFor(() => expect(screen.queryByText("K7QM 4XPT")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Add owner" })).toBeInTheDocument();
  });

  test("Remove asks first, then un-pairs just that owner", async () => {
    two();
    renderChannelsPage(`/channels/${TEAM.uid}`);
    const rows = await screen.findAllByTestId("channel-owner");
    fireEvent.click(within(rows[1]).getByRole("button", { name: "Remove" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Remove Ann Lee from");
    expect(dialog).toHaveTextContent("Other owners are not affected");
    expect(removeChannelPerson).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(removeChannelPerson).toHaveBeenCalledWith(TEAM.uid, "ann"));
  });

  test("removing the only owner is allowed and warns the channel will answer nobody", async () => {
    renderChannelsPage(`/channels/${TEAM.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("the only owner");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(removeChannelPerson).toHaveBeenCalledWith(TEAM.uid, "alex"));
  });
});

test("delete confirms, keeps conversations, and leaves the channel's address", async () => {
  renderChannelsPage(`/channels/${TEAM.uid}/settings`);
  fireEvent.click(await screen.findByRole("button", { name: "Delete…" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("conversations stay in Conversations");
  h.channels = h.channels.filter((c) => (c as ResourceOut).uid !== TEAM.uid);
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete channel" }));
  await waitFor(() =>
    expect(h.client.DELETE).toHaveBeenCalledWith("/resources/{uid}", {
      params: { path: { uid: TEAM.uid } },
    }),
  );
  await waitFor(() => expect(where.url).not.toBe(`/channels/${TEAM.uid}`));
});
