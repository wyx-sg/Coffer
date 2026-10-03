// frontend/src/components/channel/ChannelPairDialog.test.tsx
// The add-an-owner dialog carries the whole flow: opening it requests the
// code, waiting turns into a success naming the person, and every way out
// short of success withdraws the code. Only the channel requests are mocked.
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import type { ChannelStatus } from "@/lib/api/channels";
import { acceptance } from "@/test/acceptance";
import { makeChannel, makeStatus } from "@/test/channelKit";
import { ChannelPairDialog } from "./ChannelPairDialog";

const h = vi.hoisted(() => ({ status: undefined as unknown, expiresInMs: 58 * 60_000 }));

vi.mock("@/lib/api/channels", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/channels")>()),
  getChannelStatus: vi.fn(async () => h.status),
  issuePairingCode: vi.fn(async () => ({
    code: "K7QM4XPT",
    expires_at: new Date(Date.now() + h.expiresInMs).toISOString(),
    pair_url: "",
  })),
  cancelPairingCode: vi.fn(async () => undefined),
}));

const { cancelPairingCode, issuePairingCode } = await import("@/lib/api/channels");
const CH = makeChannel();

function Host({ qc }: { qc: QueryClient }) {
  const [open, setOpen] = useState(false);
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <button onClick={() => setOpen(true)}>open</button>
        <ChannelPairDialog uid={CH.uid} platform="seatalk" open={open} onOpenChange={setOpen} />
      </ToastProvider>
    </QueryClientProvider>
  );
}

function setup() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(<Host qc={qc} />);
  return qc;
}

beforeEach(() => {
  h.status = makeStatus(CH, { people: [] });
  h.expiresInMs = 58 * 60_000;
});
afterEach(() => vi.clearAllMocks());

describe("add an owner dialog", () => {
  test("renders nothing, and requests no code, until it is opened", () => {
    setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByTestId("channel-pairing-code")).not.toBeInTheDocument();
    expect(issuePairingCode).not.toHaveBeenCalled();
  });

  test("opening requests a code and shows it with the waiting state", async () => {
    setup();
    fireEvent.click(screen.getByText("open"));
    expect(await screen.findByText("K7QM 4XPT")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("Add an owner");
    expect(screen.getByText("Waiting for your message…")).toBeInTheDocument();
    expect(
      screen.getByText(/open a direct chat with .+ and send exactly this code/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Expires in 5\d min · single use/)).toBeInTheDocument();
    expect(issuePairingCode).toHaveBeenCalledWith(CH.uid, undefined);
  });

  test("somebody pairing shows who, and Done closes without withdrawing", async () => {
    const qc = setup();
    fireEvent.click(screen.getByText("open"));
    await screen.findByText("K7QM 4XPT");
    const base = makeStatus(CH, { people: [] });
    h.status = {
      ...base,
      people: [
        {
          sender_id: "ann",
          display_name: "Ann Lee",
          chat_id: "c-2",
          paired_at: new Date(Date.now() + 1000).toISOString(),
          active_conversation_id: null,
        },
      ],
    } satisfies ChannelStatus;
    await act(async () => {
      await qc.invalidateQueries();
    });
    expect(await screen.findByTestId("pair-success")).toHaveTextContent("Added Ann Lee");
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(cancelPairingCode).not.toHaveBeenCalled();
  });

  test("Esc withdraws the outstanding code", async () => {
    setup();
    fireEvent.click(screen.getByText("open"));
    await screen.findByText("K7QM 4XPT");
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(cancelPairingCode).toHaveBeenCalledWith(CH.uid));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText("K7QM 4XPT")).not.toBeInTheDocument();
  });

  test("Done closes while waiting and leaves a code the person may have sent", async () => {
    setup();
    fireEvent.click(screen.getByText("open"));
    await screen.findByText("K7QM 4XPT");
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(cancelPairingCode).not.toHaveBeenCalled();
  });

  test("New code replaces the code while waiting", async () => {
    setup();
    fireEvent.click(screen.getByText("open"));
    await screen.findByText("K7QM 4XPT");
    fireEvent.click(screen.getByRole("button", { name: "New code" }));
    await waitFor(() => expect(issuePairingCode).toHaveBeenCalledTimes(2));
  });

  acceptance("channels", "an expired pairing code is struck through in place", async () => {
    h.expiresInMs = -1000;
    setup();
    fireEvent.click(screen.getByText("open"));
    expect(await screen.findByText("Expired")).toBeInTheDocument();
    expect(screen.getByText(/The code ran out after an hour/)).toBeInTheDocument();
    expect(screen.getByText("K7QM 4XPT")).toHaveClass("line-through");
    expect(screen.queryByRole("button", { name: "Copy" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate a new code" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(cancelPairingCode).toHaveBeenCalledWith(CH.uid));
  });

  test("an expired code offers a new one, which is requested again", async () => {
    h.expiresInMs = -1000;
    setup();
    fireEvent.click(screen.getByText("open"));
    expect(await screen.findByText("Expired")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Generate a new code" }));
    await waitFor(() => expect(issuePairingCode).toHaveBeenCalledTimes(2));
  });
});
