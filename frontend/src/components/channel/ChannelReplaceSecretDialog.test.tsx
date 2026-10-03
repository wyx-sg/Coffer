// frontend/src/components/channel/ChannelReplaceSecretDialog.test.tsx
// Replace token / secret checks the pasted value against the platform as it
// lands (spec channels "Check credentials before they are saved") and says
// whether it is the bot the channel already had, so the person knows if the
// pairing still holds. The save path itself is covered in ChannelSettingsTab.test.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import { makeChannel } from "@/test/channelKit";
import { ChannelReplaceSecretDialog } from "./ChannelReplaceSecretDialog";

const h = vi.hoisted(() => ({ check: {} as Record<string, unknown> }));

vi.mock("@/lib/api/channels", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/channels")>()),
  getChannelStatus: vi.fn(async () => {
    const { makeStatus, makeChannel } = await import("@/test/channelKit");
    return makeStatus(makeChannel(), {
      people: [
        {
          sender_id: "alex",
          display_name: "Alex Chen",
          chat_id: "c",
          paired_at: new Date().toISOString(),
          active_conversation_id: null,
        },
      ],
    });
  }),
  validateCredentials: vi.fn(async () => h.check),
}));

const { validateCredentials } = await import("@/lib/api/channels");
const CH = makeChannel({
  config: { channel_type: "telegram", bot_token_ref: "channel/x/bot-token" },
});

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <ChannelReplaceSecretDialog channel={CH} open onOpenChange={() => {}} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText(/^bot token/i), { target: { value: "7314:AAHnewtoken" } });
}

afterEach(() => vi.clearAllMocks());

describe("replace token", () => {
  test("a working token for the same bot says the pairing still holds", async () => {
    h.check = {
      ok: true,
      bot_handle: "alexc_coffer_bot",
      bot_name: null,
      same_bot: true,
      reason: null,
      detail: null,
    };
    setup();
    expect(
      await screen.findByText("Works — this is @alexc_coffer_bot", {}, { timeout: 3000 }),
    ).toBeVisible();
    expect(
      await screen.findByText("Same bot as before, so the pairing with Alex Chen still holds."),
    ).toBeVisible();
    // The check addresses the stored channel, so the daemon can compare.
    expect(validateCredentials).toHaveBeenCalledWith({
      platform: "telegram",
      channel_uid: CH.uid,
      bot_token: "7314:AAHnewtoken",
    });
    expect(screen.getByRole("button", { name: "Replace and restart" })).toBeEnabled();
  });

  test("a rejected token is named under the field and blocks the replace", async () => {
    h.check = {
      ok: false,
      bot_handle: null,
      bot_name: null,
      same_bot: null,
      reason: "rejected",
      detail: "Unauthorized",
    };
    setup();
    expect(
      await screen.findByText("The platform rejected these credentials.", {}, { timeout: 3000 }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Replace and restart" })).toBeDisabled();
  });

  test("a different bot is said to lose the pairing", async () => {
    h.check = {
      ok: true,
      bot_handle: "other_bot",
      bot_name: null,
      same_bot: false,
      reason: null,
      detail: null,
    };
    setup();
    expect(
      await screen.findByText(/A different bot from before/, {}, { timeout: 3000 }),
    ).toBeVisible();
  });
});
