// frontend/src/pages/ChannelDetailPage.test.tsx
//
// The channel operating surface (spec channels, User Stories 2 + 8). Data hooks
// and the generic resource mutations are mocked so the test asserts the
// page's own rendering: status (peer + callback), pairing-code generation,
// the machine card (which machine runs the adapter, and rebinding it), and
// the header reach control's wiring.
//
// The machine card and the reach control are deliberately tested apart: they
// sit a header away from each other and answer different questions — which
// MACHINE runs the adapter, and which AGENTS the channel may drive — and a
// test that conflated them would be the first place the UI does too.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ChannelDetailPage } from "./ChannelDetailPage";
import { acceptance } from "@/test/acceptance";
import { ApiError } from "@/lib/api/errors";
import type { ChannelStatus, PairingCode } from "@/lib/api/channels";

vi.mock("@/lib/hooks/useResources", () => ({ useResource: vi.fn() }));
vi.mock("@/lib/hooks/useChannels", () => ({
  CHANNEL_KIND: "channel",
  useChannelStatus: vi.fn(),
  useIssuePairingCode: vi.fn(),
  useUpdateChannel: vi.fn(),
  useRebindChannel: vi.fn(),
  useNotifyChannel: vi.fn(),
}));
// The machine card joins the binding against the registry and this machine's
// id. Both are stubbed: the page renders without a QueryClientProvider, and
// the four binding states are set up directly rather than through a daemon.
vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn() }));
vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn() }));
vi.mock("@/lib/hooks/useAgentProviders", () => ({
  useAgentProviders: vi.fn(() => ({ data: [] })),
}));
// The header carries ScopeControl now. On a detail page it fetches its own
// scope, so the hooks behind it are stubbed rather than served by a real client.
// `channel` declares scope, so the control's panel offers all three states.
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: { scope: null, supports_scope: true } })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "cc" }] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(),
  useDisableResource: vi.fn(),
  useDeleteResource: vi.fn(),
}));

const { useResource } = await import("@/lib/hooks/useResources");
const {
  useChannelStatus,
  useIssuePairingCode,
  useUpdateChannel,
  useRebindChannel,
  useNotifyChannel,
} = await import("@/lib/hooks/useChannels");
const { useMachines } = await import("@/lib/hooks/useMachines");
const { useSyncStatus } = await import("@/lib/hooks/useSync");
const { useEnableResource, useDisableResource, useDeleteResource } =
  await import("@/lib/hooks/useResourceMutations");

const useResourceMock = vi.mocked(useResource);
const useChannelStatusMock = vi.mocked(useChannelStatus);
const useIssuePairingCodeMock = vi.mocked(useIssuePairingCode);
const useUpdateChannelMock = vi.mocked(useUpdateChannel);
const useNotifyChannelMock = vi.mocked(useNotifyChannel);

type MutationStub = { mutate: ReturnType<typeof vi.fn>; isPending: boolean };

function mutationStub(): MutationStub {
  return { mutate: vi.fn(), isPending: false };
}

/** This machine, and the other machine in the registry. */
const HERE = "machine-here";
const THERE = "machine-there";

const REGISTRY = [
  { machine_id: HERE, name: "Laptop", is_self: true },
  { machine_id: THERE, name: "Desktop", is_self: false },
];

function stubMachines(machines = REGISTRY) {
  vi.mocked(useMachines).mockReturnValue({ data: { machines } } as unknown as ReturnType<
    typeof useMachines
  >);
}

function stubResource(enabled = true, runsOn: string | null = HERE) {
  useResourceMock.mockReturnValue({
    data: {
      kind: "channel",
      name: "st",
      config: {
        channel_type: "seatalk",
        default_agent: "builtin",
        ...(runsOn === null ? {} : { runs_on: runsOn }),
      },
      enabled,
    },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useResource>);
}

function stubStatus(status: Partial<ChannelStatus> = {}) {
  useChannelStatusMock.mockReturnValue({
    data: {
      name: "st",
      channel_type: "seatalk",
      enabled: true,
      running: true,
      pending_pairing: false,
      peer: null,
      callback: null,
      runs_on: HERE,
      runs_here: true,
      ...status,
    },
  } as unknown as ReturnType<typeof useChannelStatus>);
}

function stubPairing(data?: PairingCode) {
  const mutate = vi.fn();
  useIssuePairingCodeMock.mockReturnValue({
    mutate,
    isPending: false,
    data,
  } as unknown as ReturnType<typeof useIssuePairingCode>);
  return mutate;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/channels/st"]}>
      <Routes>
        <Route path="channels/:name" element={<ChannelDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

let enable: MutationStub;
let disable: MutationStub;
let del: MutationStub;
let notify: MutationStub;
let rebind: MutationStub;

beforeEach(() => {
  vi.clearAllMocks();
  enable = mutationStub();
  disable = mutationStub();
  del = mutationStub();
  notify = mutationStub();
  rebind = mutationStub();
  vi.mocked(useRebindChannel).mockReturnValue(
    rebind as unknown as ReturnType<typeof useRebindChannel>,
  );
  vi.mocked(useSyncStatus).mockReturnValue({
    data: { machine_id: HERE },
  } as unknown as ReturnType<typeof useSyncStatus>);
  stubMachines();
  vi.mocked(useEnableResource).mockReturnValue(
    enable as unknown as ReturnType<typeof useEnableResource>,
  );
  vi.mocked(useDisableResource).mockReturnValue(
    disable as unknown as ReturnType<typeof useDisableResource>,
  );
  vi.mocked(useDeleteResource).mockReturnValue(
    del as unknown as ReturnType<typeof useDeleteResource>,
  );
  useUpdateChannelMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateChannel>);
  useNotifyChannelMock.mockReturnValue(notify as unknown as ReturnType<typeof useNotifyChannel>);
});

// The UI half of the status scenario: the page queries /channels/{name}/status
// over REST and reports adapter run state, the paired peer, and the seatalk
// callback details (the CLI half lives in the backend suite).
acceptance("channels", "channel status reports runtime, pairing, and callback details", () => {
  stubResource();
  stubStatus({
    peer: {
      chat_id: "chat-77",
      display_name: "Yuxing",
      paired_at: "2026-06-12T08:00:00Z",
      active_conversation_id: "conv-1",
    },
    callback: {
      delivery: "webhook",
      port: 8466,
      path: "/seatalk/st",
      listener_running: true,
      public_base_url: null,
      public_callback_url: null,
      tunnel_managed: false,
      tunnel_running: false,
      websocket_state: null,
      websocket_error: null,
    },
  });
  stubPairing();
  renderPage();

  expect(screen.getByText("Yuxing")).toBeInTheDocument();
  expect(screen.getByText("chat-77")).toBeInTheDocument();
  expect(screen.getByText("conv-1")).toBeInTheDocument();
  expect(screen.getByText("127.0.0.1:8466/seatalk/st")).toBeInTheDocument();
});

describe("ChannelDetailPage", () => {
  test("shows 'not paired' when the channel has no peer", () => {
    stubResource();
    stubStatus({ peer: null });
    stubPairing();
    renderPage();

    expect(screen.getByText(/not paired/i)).toBeInTheDocument();
  });

  test("the pairing button issues a code and the code is shown large", () => {
    stubResource();
    stubStatus();
    const mutate = stubPairing({ code: "ABCD2345", expires_at: "2026-06-12T13:00:00Z" });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /generate pairing code/i }));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(screen.getByText("ABCD2345")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  test("the header reach control disables the channel", () => {
    stubResource(true);
    stubStatus();
    stubPairing();
    renderPage();

    // No Switch any more: the header carries the same reach control the row
    // does, so the two surfaces say the same thing about the same channel —
    // including "answer only for these agents", which a Switch cannot.
    expect(screen.queryByRole("switch")).toBeNull();
    const reach = within(screen.getByTestId("scope-control")).getByRole("button");
    expect(reach).toHaveTextContent(/every agent/i);
    fireEvent.click(reach);
    expect(screen.getByRole("radio", { name: /only selected agents/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /^disabled$/i }));
    expect(disable.mutate).toHaveBeenCalledWith({ kind: "channel", name: "st" });
    expect(enable.mutate).not.toHaveBeenCalled();
  });

  test("delete asks for confirmation, then deletes the resource", () => {
    stubResource();
    stubStatus();
    stubPairing();
    renderPage();

    // The header button's accessible name is its aria-label ("Delete channel");
    // the confirm dialog's confirm button is plain "Delete".
    fireEvent.click(screen.getByRole("button", { name: /^delete channel$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(del.mutate).toHaveBeenCalledWith({ kind: "channel", name: "st" }, expect.anything());
  });

  test("the edit button opens the edit dialog", () => {
    stubResource();
    stubStatus();
    stubPairing();
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /^edit channel$/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/edit channel/i);
  });

  test("send test message is disabled until a peer is paired", () => {
    stubResource();
    stubStatus({ peer: null });
    stubPairing();
    renderPage();

    // Card title, field label and button each say their own thing — "Send
    // test message" no longer appears three times over.
    expect(screen.getByText("Test delivery")).toBeInTheDocument();
    expect(screen.getByLabelText(/^message$/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
  });

  test("sending a test message calls notify with the typed text", () => {
    stubResource();
    stubStatus({
      peer: {
        chat_id: "chat-1",
        display_name: "Yuxing",
        paired_at: "2026-06-12T08:00:00Z",
        active_conversation_id: null,
      },
    });
    stubPairing();
    renderPage();

    fireEvent.change(screen.getByLabelText(/^message$/i), { target: { value: "ping" } });
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));
    expect(notify.mutate).toHaveBeenCalledWith("ping");
  });

  test("the header carries the platform chip, a back link, and a stopped adapter reads as attention", () => {
    stubResource();
    stubStatus({ running: false });
    stubPairing();
    renderPage();

    expect(screen.getByRole("heading", { name: "st" })).toBeInTheDocument();
    expect(screen.getByText("SeaTalk")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to channels/i })).toHaveAttribute(
      "href",
      "/channels",
    );
    // The same warn tone the list's health badge uses for a stopped adapter —
    // not the brand colour, not muted.
    expect(screen.getByText("Stopped")).toHaveClass("text-status-warn");
  });

  test("a missing channel shows the shared empty state with the translated error", () => {
    useResourceMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: new ApiError("RESOURCE_NOT_FOUND", "raw server text"),
    } as unknown as ReturnType<typeof useResource>);
    stubStatus();
    stubPairing();
    renderPage();

    expect(screen.getAllByText(/not found/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("raw server text")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /back to channels/i }).length).toBeGreaterThan(0);
  });
});

describe("ChannelDetailPage — the machine that runs the channel", () => {
  /** The picker, by its accessible name. It is a row of the status card: the
   *  binding is the other half of that card's "Running" headline, not a
   *  separate subject needing its own heading. */
  const picker = () => screen.getByRole("combobox", { name: /machine running st/i });

  test("the binding is a row of the status card, naming this machine", () => {
    stubResource();
    stubStatus({ runs_on: HERE, runs_here: true });
    stubPairing();
    renderPage();

    // Next to the adapter's own state, because "Running" is only believable
    // once you know which machine it is running on.
    const card = screen.getByTestId("channel-status-card");
    expect(within(card).getByText(/^runs on$/i)).toBeInTheDocument();
    expect(within(card).getByRole("combobox", { name: /machine running st/i })).toBeInTheDocument();
    expect(picker()).toHaveTextContent(/Laptop · this machine/i);
  });

  test("names the other machine, so a stopped adapter here reads as normal", () => {
    stubResource(true, THERE);
    stubStatus({ running: false, runs_on: THERE, runs_here: false });
    stubPairing();
    renderPage();

    // Bound elsewhere is somebody's choice, not a fault: the picker reports it
    // and nothing raises an alarm.
    expect(picker()).toHaveTextContent(/Desktop/i);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("reports a binding no machine claims as a fault", () => {
    stubResource(true, "machine-gone");
    stubStatus({ running: false, runs_on: "machine-gone", runs_here: false });
    stubPairing();
    renderPage();

    // It runs NOWHERE — the one binding state that nothing but a rebind fixes.
    expect(screen.getByRole("alert")).toHaveTextContent(/machine-gone/);
    expect(screen.getByRole("alert")).toHaveTextContent(/runs nowhere/i);
  });

  test("an unbound channel is reported here and by the daemon's own diagnostic", () => {
    stubResource(true, null);
    stubStatus({
      running: false,
      runs_on: null,
      runs_here: false,
      diagnostics: [
        { code: "channel_not_bound", message: "This channel is not bound to a machine." },
      ],
    });
    stubPairing();
    renderPage();

    // The status card renders the daemon's diagnostic verbatim …
    expect(screen.getByText(/This channel is not bound to a machine\./)).toBeInTheDocument();
    // … and the machine card says the same thing next to the control that
    // fixes it, which is the only place the user can act on it.
    expect(screen.getByText(/no daemon starts it and the bot never answers/i)).toBeInTheDocument();
    expect(picker()).toHaveTextContent(/not bound/i);
  });

  test("rebinding writes the binding into the channel's own config", () => {
    stubResource();
    stubStatus({ runs_on: HERE, runs_here: true });
    stubPairing();
    renderPage();

    // jsdom has no PointerEvent; Radix opens the listbox from the keyboard.
    fireEvent.keyDown(picker(), { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "Desktop" }));

    expect(rebind.mutate).toHaveBeenCalledWith({
      config: { channel_type: "seatalk", default_agent: "builtin", runs_on: HERE },
      runsOn: THERE,
      machine: "Desktop",
    });
  });

  test("the rebind menu states the handover timing and that this is not reach", () => {
    // Both are things the user cannot see and would otherwise meet as a bug:
    // a rebind that is not instant on the far side, and a reach control one
    // row away that answers an entirely different question. They live in the
    // menu now rather than in prose beside it — this is the moment the choice
    // is actually made.
    stubResource();
    stubStatus();
    stubPairing();
    renderPage();

    // jsdom has no PointerEvent; open the Radix listbox from the keyboard.
    fireEvent.keyDown(picker(), { key: "ArrowDown" });

    expect(screen.getByText(/needs no restart/i)).toBeInTheDocument();
    expect(screen.getByText(/which agents this channel may drive/i)).toBeInTheDocument();
  });
});

describe("ChannelDetailPage — platform diagnostics and pairing link", () => {
  test("reports a configuration the platform will not honour", () => {
    // FR-060: privacy mode makes "act on unaddressed group messages" a setting
    // that reads correctly in Coffer and does nothing in the chat.
    stubResource();
    stubStatus({
      diagnostics: [
        {
          code: "telegram_privacy_mode",
          message: "Disable privacy mode in BotFather (/setprivacy), then re-add the bot.",
        },
      ],
    });
    stubPairing();
    renderPage();

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Disable privacy mode in BotFather");
  });

  test("shows no alert when nothing contradicts the configuration", () => {
    stubResource();
    stubStatus({ diagnostics: [] });
    stubPairing();
    renderPage();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("offers the pairing link alongside the code", () => {
    // FR-066: one tap instead of transcribing eight characters on a phone.
    stubResource();
    stubStatus();
    stubPairing({
      code: "ABCD2345",
      expires_at: "2026-06-12T10:00:00Z",
      pair_url: "https://t.me/cofferbot?start=ABCD2345",
    });
    renderPage();

    expect(screen.getByText("ABCD2345")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /pairing link/i })).toHaveAttribute(
      "href",
      "https://t.me/cofferbot?start=ABCD2345",
    );
  });

  test("shows only the code when the platform has no pairing link", () => {
    stubResource();
    stubStatus();
    stubPairing({ code: "ABCD2345", expires_at: "2026-06-12T10:00:00Z" });
    renderPage();

    expect(screen.getByText("ABCD2345")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /pairing link/i })).not.toBeInTheDocument();
  });
});
