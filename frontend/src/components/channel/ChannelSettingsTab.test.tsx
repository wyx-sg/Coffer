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

import { MemoryRouter } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ResourceOut } from "@/lib/api/resources";
import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { ChannelReplaceSecretDialog } from "./ChannelReplaceSecretDialog";
import { ChannelSettingsTab } from "./ChannelSettingsTab";
import { AGENT, HERE, REGISTRY, makeChannel, makeSettings } from "@/test/channelKit";

const SECRETS = {
  refs: [
    {
      ref: "channel/9a/bot-token",
      label: "Telegram token",
      present: true,
      locked: false,
      cited_by: [],
      bindings: [],
      mentioned_by_skills: [],
    },
    {
      ref: "secret/other",
      label: "Other bot",
      present: true,
      locked: false,
      cited_by: [],
      bindings: [],
      mentioned_by_skills: [],
    },
  ],
};
vi.mock("@/lib/hooks/useSecrets", () => ({
  useSecrets: () => ({ data: SECRETS }),
}));

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
      <MemoryRouter>
        <TooltipProvider>{ui}</TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderSettings(channel: ResourceOut = makeChannel()) {
  return wrap(
    <ChannelSettingsTab
      channel={channel}
      settings={makeSettings(channel)}
      workspaceDirectory="/home/me/.coffer/content/workspace"
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

  test("the secret row shows the secret's name and Replace key", () => {
    renderSettings(TG);
    expect(screen.getByRole("link", { name: "Telegram token" })).toBeVisible();
    expect(screen.getByRole("button", { name: /replace key/i })).toBeVisible();
    expect(screen.queryByText("••••••••••••")).toBeNull();
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
  acceptance("channels", "the step lines are hidden in the channel's settings", async () => {
    const api = installApi();
    renderSettings(TG);

    fireEvent.click(screen.getByRole("switch", { name: /show step lines/i }));
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(patched(api, 0).show_steps).toBe(false);
  });

  test("a SeaTalk channel, which shows only typing while a turn runs, offers no step lines", () => {
    installApi();
    renderSettings();

    expect(screen.queryByRole("switch", { name: /show step lines/i })).toBeNull();
    expect(screen.queryByLabelText(/long-task ping after/i)).toBeNull();
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
  acceptance("channels", "the channel's directories are edited on the Channels page", async () => {
    const api = installApi();
    renderSettings(makeChannel({ config: { directories: ["/srv/app", "/srv/lib"] } }));
    fireEvent.click(screen.getByRole("button", { name: "Remove /srv/app" }));

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(patched(api).directories).toEqual(["/srv/lib"]);
  });

  acceptance(
    "channels",
    "the channel's default directory is edited on the Channels page",
    async () => {
      const api = installApi();
      renderSettings(makeChannel({ config: { directories: ["/srv/app", "/srv/lib"] } }));
      fireEvent.click(screen.getByRole("button", { name: "Set /srv/lib as the default" }));

      await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
      expect(patched(api).default_agent_config).toEqual({ cwd: "/srv/lib" });
      // The listed default is marked as such, and can be unset.
      expect(screen.getByTestId("channel-directories")).toHaveTextContent(/default/);
      expect(
        screen.getByRole("button", { name: "Stop starting new conversations in /srv/lib" }),
      ).toBeInTheDocument();
    },
  );

  test("removing the default directory also clears the default", async () => {
    const api = installApi();
    renderSettings(
      makeChannel({
        config: { directories: ["/srv/app"], default_agent_config: { cwd: "/srv/app" } },
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove /srv/app" }));
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(patched(api).directories).toEqual([]);
    expect(patched(api).default_agent_config ?? {}).not.toHaveProperty("cwd");
  });

  test("a default set outside the list is shown in it", () => {
    installApi();
    renderSettings(makeChannel({ config: { default_agent_config: { cwd: "/srv/old" } } }));
    const list = screen.getByRole("list", { name: "Directories" });
    expect(list).toHaveTextContent("/srv/old");
    expect(list).toHaveTextContent(/default/);
  });

  test("with no default marked, Coffer's workspace is shown as the default", () => {
    installApi();
    renderSettings(makeChannel({ config: { directories: ["/srv/app"] } }));
    const list = screen.getByRole("list", { name: "Directories" });
    expect(list).toHaveTextContent("/home/me/.coffer/content/workspace");
    expect(list).toHaveTextContent("default · Coffer workspace");
  });

  test("a marked default replaces the workspace row", () => {
    installApi();
    renderSettings(
      makeChannel({
        config: { directories: ["/srv/app"], default_agent_config: { cwd: "/srv/app" } },
      }),
    );
    expect(screen.getByRole("list", { name: "Directories" })).not.toHaveTextContent(
      "/home/me/.coffer/content/workspace",
    );
  });

  test("a long list scrolls inside its box", () => {
    installApi();
    const directories = Array.from({ length: 20 }, (_, i) => `/srv/d${i}`);
    renderSettings(makeChannel({ config: { directories } }));
    expect(screen.getByRole("list", { name: "Directories" })).toHaveClass(
      "max-h-64",
      "overflow-y-auto",
    );
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

test("picking another stored secret re-points the channel and writes no value", async () => {
  const api = installApi();
  wrap(<ChannelReplaceSecretDialog channel={TG} open onOpenChange={() => {}} />);

  const dialog = screen.getByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: /use another secret/i }));
  fireEvent.click(within(dialog).getByRole("combobox"));
  fireEvent.click(await screen.findByText("Other bot"));
  fireEvent.click(within(dialog).getByRole("button", { name: /use this secret/i }));

  await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
  const config = patched(api);
  expect(config.bot_token_ref).toBe("secret/other");
  expect(config.default_agent).toBe(AGENT.uid);
  expect(api.POST).not.toHaveBeenCalled();
});

describe("system prompts", () => {
  const section = () => screen.getByTestId("channel-system-prompts");
  const openDialog = () =>
    fireEvent.click(within(section()).getByRole("button", { name: /edit system prompts/i }));

  acceptance(
    "channels",
    "the system prompts are edited through a dialog on the Settings tab",
    async () => {
      const api = installApi();
      renderSettings(
        makeChannel({ config: { group_system_prompt: "Name the ticket first.\nBe brief." } }),
      );

      // Shown as written; an empty prompt is a blank row, with no placeholder.
      expect(within(section()).getByText(/Name the ticket first\./)).toBeInTheDocument();
      expect(within(section()).queryByRole("textbox")).toBeNull();

      openDialog();
      const dialog = screen.getByRole("dialog");
      const direct = within(dialog).getByLabelText("Direct chats");
      const group = within(dialog).getByLabelText("Group chats");
      expect(direct).toHaveValue("");
      expect(direct).not.toHaveAttribute("placeholder");
      expect(group).toHaveValue("Name the ticket first.\nBe brief.");

      fireEvent.change(direct, { target: { value: "  Answer in Chinese.\n" } });
      fireEvent.change(group, { target: { value: "" } });
      expect(api.PATCH).not.toHaveBeenCalled(); // nothing is saved until Save
      fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

      await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
      expect(patched(api)).toMatchObject({
        direct_system_prompt: "Answer in Chinese.",
        group_system_prompt: "",
        app_secret_ref: "channel/0f/app-secret", // every ref goes back as it was
      });
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    },
  );

  test("Cancel discards the draft and saves nothing", async () => {
    const api = installApi();
    renderSettings(TG);
    openDialog();
    fireEvent.change(within(screen.getByRole("dialog")).getByLabelText("Direct chats"), {
      target: { value: "Answer in Chinese." },
    });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.PATCH).not.toHaveBeenCalled();
    openDialog();
    expect(within(screen.getByRole("dialog")).getByLabelText("Direct chats")).toHaveValue("");
  });

  acceptance("channels", "a system prompt longer than 4,000 characters is refused", async () => {
    const api = installApi();
    renderSettings(TG);
    openDialog();
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Group chats"), {
      target: { value: "x".repeat(4001) },
    });

    expect(within(dialog).getByRole("alert")).toHaveTextContent("At most 4000 characters.");
    expect(within(dialog).getByText("4001 / 4000")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
    expect(api.PATCH).not.toHaveBeenCalled();
  });

  test("a refused save keeps the dialog open with what was typed", async () => {
    const api = installApi(
      mockApiClient({
        PATCH: vi.fn().mockResolvedValue({
          error: { error: { code: "VALIDATION_ERROR", message: "too long" } },
          response: new Response(null, { status: 422 }),
        }),
      }),
    );
    renderSettings(TG);
    openDialog();
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Direct chats"), {
      target: { value: "Answer in Chinese." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "Save" })).not.toBeDisabled(),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Direct chats")).toHaveValue("Answer in Chinese.");
  });
});
