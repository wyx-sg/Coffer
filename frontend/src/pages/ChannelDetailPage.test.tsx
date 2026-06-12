// frontend/src/pages/ChannelDetailPage.test.tsx
//
// The channel operating surface (spec 009, User Stories 2 + 8). Data hooks
// and the generic resource mutations are mocked so the test asserts the
// page's own rendering: status (peer + callback), pairing-code generation,
// and the enable/disable toggle wiring.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ChannelDetailPage } from "./ChannelDetailPage";
import { acceptance } from "@/test/acceptance";
import type { ChannelStatus, PairingCode } from "@/lib/api/channels";

vi.mock("@/lib/hooks/useResources", () => ({ useResource: vi.fn() }));
vi.mock("@/lib/hooks/useChannels", () => ({
  CHANNEL_KIND: "channel",
  useChannelStatus: vi.fn(),
  useIssuePairingCode: vi.fn(),
  useUpdateChannel: vi.fn(),
  useNotifyChannel: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(),
  useDisableResource: vi.fn(),
  useDeleteResource: vi.fn(),
}));

const { useResource } = await import("@/lib/hooks/useResources");
const { useChannelStatus, useIssuePairingCode, useUpdateChannel, useNotifyChannel } =
  await import("@/lib/hooks/useChannels");
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

function stubResource(enabled = true) {
  useResourceMock.mockReturnValue({
    data: {
      kind: "channel",
      name: "st",
      config: { channel_type: "seatalk", default_agent: "builtin" },
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

beforeEach(() => {
  vi.clearAllMocks();
  enable = mutationStub();
  disable = mutationStub();
  del = mutationStub();
  notify = mutationStub();
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
  useNotifyChannelMock.mockReturnValue(
    notify as unknown as ReturnType<typeof useNotifyChannel>,
  );
});

// The UI half of the status scenario: the page queries /channels/{name}/status
// over REST and reports adapter run state, the paired peer, and the seatalk
// callback details (the CLI half lives in the backend suite).
acceptance("009-channels", "channel status reports runtime, pairing, and callback details", () => {
  stubResource();
  stubStatus({
    peer: {
      chat_id: "chat-77",
      display_name: "Yuxing",
      paired_at: "2026-06-12T08:00:00Z",
      active_conversation_id: "conv-1",
    },
    callback: { port: 8466, path: "/seatalk/st", listener_running: true },
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

  test("toggling the enabled switch calls the disable mutation", () => {
    stubResource(true);
    stubStatus();
    stubPairing();
    renderPage();

    fireEvent.click(screen.getByRole("switch"));
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

    expect(screen.getByRole("button", { name: /send test message/i })).toBeDisabled();
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

    fireEvent.change(screen.getByLabelText(/test message/i), { target: { value: "ping" } });
    fireEvent.click(screen.getByRole("button", { name: /send test message/i }));
    expect(notify.mutate).toHaveBeenCalledWith("ping");
  });
});
