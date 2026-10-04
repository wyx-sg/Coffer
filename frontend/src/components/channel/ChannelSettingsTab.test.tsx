// frontend/src/components/channel/ChannelSettingsTab.test.tsx
//
// A channel's Settings save as they change (no Save button): a switch PATCHes
// at once, a typed value a moment after typing stops — and only when valid;
// an invalid value shows its error and is never sent. Every PATCH carries the
// whole config back with every secret ref untouched, and two saves a
// moment apart never undo each other. Replacing a secret writes the new value
// under the ref the channel already cites; the daemon restarts the adapter.
//
// The PATCH is addressed to the channel's uid; the fixtures spell uid and
// name differently so an assertion about the address cannot pass on the label.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { ResourceOut } from "@/lib/api/resources";
import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { ChannelReplaceSecretDialog } from "./ChannelReplaceSecretDialog";
import { ChannelSettingsTab } from "./ChannelSettingsTab";
import { AGENT, HERE, REGISTRY, makeChannel, makeSettings } from "@/test/channelKit";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: () => ({ data: { machines: REGISTRY } }),
  useThisMachineId: () => ({ machineId: HERE, isPending: false }),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [AGENT] }) }));

const { getApiClient } = await import("@/lib/api/client");

function installApi(api: ApiClientMock = mockApiClient()) {
  vi.mocked(getApiClient).mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

const TG = makeChannel({
  uid: "u-3d9a1f77",
  name: "tg",
  config: {
    channel_type: "telegram",
    bot_token_ref: "channel/9a/bot-token",
    app_id: undefined,
    app_secret_ref: undefined,
  },
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>,
  );
}

function renderSettings(channel: ResourceOut = makeChannel()) {
  return wrap(
    <ChannelSettingsTab
      channel={channel}
      settings={makeSettings(channel)}
      onReplaceSecret={() => {}}
      onDelete={() => {}}
    />,
  );
}

/** The config the n-th PATCH sent. */
function patched(api: ApiClientMock, nth = 0): Record<string, unknown> {
  return (api.PATCH.mock.calls[nth][1] as { body: { config: Record<string, unknown> } }).body
    .config;
}

const SLOW = { timeout: 2500 };

beforeEach(() => installApi());
afterEach(() => vi.clearAllMocks());

describe("message batching", () => {
  const textField = () => screen.getByLabelText(/wait after a text message/i);
  const forwardField = () => screen.getByLabelText(/wait after a forward or files/i);

  acceptance("channels", "the quiet windows are edited on the Channels page", async () => {
    const api = installApi();
    renderSettings(
      makeChannel({ config: { wait_after_text_seconds: 3, wait_after_forward_seconds: 10 } }),
    );

    expect(textField()).toHaveValue(3);
    expect(forwardField()).toHaveValue(10);
    fireEvent.change(textField(), { target: { value: "0" } });

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1), SLOW);
    expect(api.PATCH.mock.calls[0][1]).toMatchObject({ params: { path: { uid: "u-c0be4512" } } });
    const config = patched(api);
    expect(config.wait_after_text_seconds).toBe(0);
    expect(config.wait_after_forward_seconds).toBe(10);
    // Every ref and platform field goes back as it was.
    expect(config.app_secret_ref).toBe("channel/0f/app-secret");
    expect(config.runs_on).toBe(HERE);
  });

  test("an out-of-range value shows its error and is not saved", async () => {
    const api = installApi();
    renderSettings();

    fireEvent.change(forwardField(), { target: { value: "61" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/0 to 60/);
    await new Promise((r) => setTimeout(r, 900));
    expect(api.PATCH).not.toHaveBeenCalled();
  });
});

describe("replies", () => {
  test("the step lines switch saves at once; the ping threshold after typing stops", async () => {
    const api = installApi();
    renderSettings();

    fireEvent.click(screen.getByRole("switch", { name: /show step lines/i }));
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(patched(api, 0).show_steps).toBe(false);

    fireEvent.change(screen.getByLabelText(/long-task ping after/i), {
      target: { value: "300" },
    });
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(2), SLOW);
    // The second save plans from what the first wrote, so it keeps it.
    expect(patched(api, 1)).toMatchObject({ show_steps: false, notify_after_seconds: 300 });
  });

  test("a blank threshold is refused inline and never sent", async () => {
    const api = installApi();
    renderSettings();
    fireEvent.change(screen.getByLabelText(/long-task ping after/i), {
      target: { value: "" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/0 to 3600/);
    await new Promise((r) => setTimeout(r, 900));
    expect(api.PATCH).not.toHaveBeenCalled();
  });
});

describe("conversations", () => {
  const idleField = () => screen.getByLabelText(/start a new conversation after/i);

  acceptance("channels", "the idle period comes from the channel's settings", async () => {
    const api = installApi();
    renderSettings(makeChannel({ config: { new_conversation_after_idle_hours: 24 } }));

    expect(idleField()).toHaveValue(24);
    fireEvent.change(idleField(), { target: { value: "6" } });

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1), SLOW);
    expect(patched(api).new_conversation_after_idle_hours).toBe(6);
    // Zero is a value, not an empty field: it turns the rollover off.
    fireEvent.change(idleField(), { target: { value: "0" } });
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(2), SLOW);
    expect(patched(api, 1).new_conversation_after_idle_hours).toBe(0);
  });

  test("a blank or out-of-range period is refused inline and never sent", async () => {
    const api = installApi();
    renderSettings();
    fireEvent.change(idleField(), { target: { value: "" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/0 to 8760/);
    await new Promise((r) => setTimeout(r, 900));
    expect(api.PATCH).not.toHaveBeenCalled();
  });
});

describe("working directories", () => {
  const defaultField = () => screen.getByLabelText(/^default$/i);

  acceptance(
    "channels",
    "the channel's directories are edited on the Channels page",
    async () => {
      const api = installApi();
      renderSettings(makeChannel({ config: { directories: ["/srv/app", "/srv/lib"] } }));
      fireEvent.click(screen.getByRole("button", { name: "Remove /srv/app" }));

      await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
      expect(patched(api).directories).toEqual(["/srv/lib"]);
    },
  );

  acceptance(
    "channels",
    "the channel's default directory is edited on the Channels page",
    async () => {
      const api = installApi();
      renderSettings(makeChannel({ config: { directories: ["/srv/app"] } }));
      fireEvent.change(defaultField(), { target: { value: "/srv/app/" } });

      await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1), SLOW);
      expect(patched(api).default_agent_config).toEqual({ cwd: "/srv/app" });
      // The listed default is marked as such.
      expect(screen.getByTestId("channel-directories")).toHaveTextContent(/default/);
    },
  );

  test("a relative default shows an inline error and saves nothing", async () => {
    const api = installApi();
    renderSettings();
    fireEvent.change(defaultField(), { target: { value: "projects" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/"projects" is not an absolute path/);
    await new Promise((r) => setTimeout(r, 900));
    expect(api.PATCH).not.toHaveBeenCalled();
  });
});

describe("group chats", () => {
  test("telegram offers require-mention; SeaTalk, which only delivers mentions, does not", async () => {
    const api = installApi();
    const { unmount } = renderSettings(TG);
    fireEvent.click(screen.getByRole("switch", { name: /only when @mentioned/i }));
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(patched(api).require_mention).toBe(false);
    unmount();

    renderSettings();
    expect(screen.queryByRole("switch", { name: /only when @mentioned/i })).toBeNull();
    expect(screen.getByRole("switch", { name: /someone else/i })).toBeInTheDocument();
  });
});

test("the SeaTalk App ID saves when changed, and refuses to save blank", async () => {
  const api = installApi();
  renderSettings();
  const field = screen.getByLabelText(/^app id$/i);
  fireEvent.change(field, { target: { value: "" } });
  expect(screen.getByRole("alert")).toHaveTextContent(/enter the app id/i);
  fireEvent.change(field, { target: { value: "9402" } });
  fireEvent.blur(field);
  await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
  expect(patched(api).app_id).toBe("9402");
});

acceptance("channels", "rotating a channel secret keeps its refs and pairing", async () => {
  // spec channels "Manage channels from the Channels page": a
  // rotation writes the new value under the ref the channel already cites,
  // then PATCHes the same channel with every ref unchanged — so the binding,
  // the pairing and the synced ciphertext address all stay where they were —
  // and the daemon restarts the adapter on the replaced secret by itself.
  const api = installApi();
  wrap(<ChannelReplaceSecretDialog channel={TG} open onOpenChange={() => {}} />);

  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText(/bot token/i), {
    target: { value: "999:rotated" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: /replace and restart/i }));

  await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
  expect(api.POST.mock.calls[0]).toEqual([
    "/secrets",
    { body: { ref: "channel/9a/bot-token", value: "999:rotated" } },
  ]);
  const config = patched(api);
  expect(config.bot_token_ref).toBe("channel/9a/bot-token");
  expect(config.default_agent).toBe(AGENT.uid);
  // Secret first: the PATCHed config must never cite a ref whose value is stale.
  expect(api.POST.mock.invocationCallOrder[0]).toBeLessThan(api.PATCH.mock.invocationCallOrder[0]);
  // Nothing else is called: no off-and-on, no restart request. The daemon sees
  // the secret change and restarts the adapter on its own.
  expect(api.POST.mock.calls.map((c) => c[0])).toEqual(["/secrets"]);
});
