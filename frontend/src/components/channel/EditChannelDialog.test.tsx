// frontend/src/components/channel/EditChannelDialog.test.tsx
//
// The edit flow's apply contract: rotating a secret writes the NEW value to
// the channel's EXISTING credential ref BEFORE the config is PATCHed, a blank
// secret field rotates nothing, and changing the bound agent PATCHes the full
// config (refs preserved) with only default_agent changed.
//
// The PATCH is addressed to the channel's `uid`, and `default_agent` holds an
// agent's `uid`. Every fixture below therefore spells its uid nothing like its
// name — a fixture where the two agreed would let an assertion about the
// address pass on the label, which is exactly the confusion the uid removes.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EditChannelDialog } from "./EditChannelDialog";
import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
// The agent picker (AgentSelect) reads the registered AGENT RESOURCES. It used
// to read the turn platform's provider registry, because the binding was a
// provider key (`claude_code`) while the scope beside it held resource names —
// two vocabularies for one thing. There is one now: the agent's uid.
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);
const { useAgents } = await import("@/lib/hooks/useAgents");
const useAgentsMock = vi.mocked(useAgents);

function installApi(api: ApiClientMock) {
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

/** The registered agents the picker offers, by name, and binds to, by uid. */
const CLAUDE = { uid: "u-6c1d0b83", name: "claude-code" };
const CODEX = { uid: "u-f04a927e", name: "codex" };

/** The two channels edited below: a uid the PATCH is addressed to, a name the
 *  credential refs and the toast spell. */
const TG_UID = "u-3d9a1f77";
const ST_UID = "u-c0be4512";

const telegramResource = {
  uid: TG_UID,
  kind: "channel",
  name: "tg",
  enabled: true,
  config: {
    channel_type: "telegram",
    bot_token_ref: "channel/tg/bot-token",
    default_agent: CLAUDE.uid,
  },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as const;

function renderDialog(resource = telegramResource) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <EditChannelDialog open onOpenChange={() => {}} resource={resource} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useAgentsMock.mockReturnValue({
    data: [CLAUDE, CODEX],
  } as unknown as ReturnType<typeof useAgents>);
});

afterEach(() => vi.clearAllMocks());

function save() {
  fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
}

describe("EditChannelDialog", () => {
  test("offers the registered agents by NAME and re-binds by uid", async () => {
    // One vocabulary, two sides of it. The menu is the agents this vault has,
    // under the names their owner gave them; the config gets the uid, which is
    // what keeps the binding pointing at the same agent after a relabel.
    const api = installApi(mockApiClient());
    renderDialog();

    const picker = screen.getByRole("combobox", { name: /default agent/i });
    fireEvent.keyDown(picker, { key: "ArrowDown" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      CLAUDE.name,
      CODEX.name,
    ]);

    fireEvent.click(screen.getByRole("option", { name: CODEX.name }));
    save();

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    const config = (api.PATCH.mock.calls[0][1] as { body: { config: Record<string, unknown> } })
      .body.config;
    expect(config.default_agent).toBe(CODEX.uid);
  });

  test("a binding this vault has no agent for is kept, and shown as the uid it is", () => {
    // Dropping it would silently re-bind the channel to whichever agent sorts
    // first. Showing the raw uid is the only thing that lets the owner see what
    // the binding actually says and fix it.
    installApi(mockApiClient());
    renderDialog({
      ...telegramResource,
      config: { ...telegramResource.config, default_agent: "u-deadbeef" },
    } as unknown as typeof telegramResource);

    expect(screen.getByRole("combobox", { name: /default agent/i })).toHaveTextContent(
      "u-deadbeef",
    );
  });

  acceptance("channels", "rotating a channel secret keeps its refs and pairing", async () => {
    // spec channels "Manage channels from the Channels page and the CLI": a
    // rotation writes the new value under the ref the channel already cites,
    // then PATCHes the same channel with every ref unchanged — so the binding,
    // the pairing and the synced ciphertext address all stay where they were.
    const api = installApi(mockApiClient());
    renderDialog();

    fireEvent.change(screen.getByLabelText(/new bot token/i), {
      target: { value: "999:rotated" },
    });
    save();

    await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(1));
    expect(api.POST).toHaveBeenCalledWith("/credentials", {
      body: { ref: "channel/tg/bot-token", value: "999:rotated" },
    });
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(api.PATCH).toHaveBeenCalledWith("/resources/{uid}", {
      params: { path: { uid: TG_UID } },
      body: {
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          default_agent: CLAUDE.uid,
        },
      },
    });
    // Secret first: the PATCHed config must never cite a ref whose value is stale.
    expect(api.POST.mock.invocationCallOrder[0]).toBeLessThan(
      api.PATCH.mock.invocationCallOrder[0],
    );
  });

  test("a blank token rotates nothing — only the config PATCH runs", async () => {
    const api = installApi(mockApiClient());
    renderDialog();
    save();

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(api.POST).not.toHaveBeenCalled();
  });

  test("telegram: the group switches start at the stored values and PATCH what changed", async () => {
    // spec channels "Configure when the bot answers in a group": both bools
    // are editable from the web. An absent key reads as the backend default
    // (mention required, other @mentions not ignored).
    const api = installApi(mockApiClient());
    renderDialog();

    const requireMention = screen.getByRole("switch", { name: /only when @mentioned/i });
    const ignoreOthers = screen.getByRole("switch", { name: /someone else/i });
    expect(requireMention).toBeChecked();
    expect(ignoreOthers).not.toBeChecked();

    fireEvent.click(requireMention);
    fireEvent.click(ignoreOthers);
    save();

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    const config = (api.PATCH.mock.calls[0][1] as { body: { config: Record<string, unknown> } })
      .body.config;
    expect(config.require_mention).toBe(false);
    expect(config.ignore_other_mentions).toBe(true);
  });

  describe("seatalk", () => {
    const seatalkChannel = {
      uid: ST_UID,
      kind: "channel",
      name: "st",
      enabled: true,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        default_agent: CLAUDE.uid,
      },
    } as unknown as typeof telegramResource;

    test("offers the app id and an app secret rotation, and nothing a webhook needed", () => {
      installApi(mockApiClient());
      renderDialog(seatalkChannel);

      expect(screen.getByLabelText(/app id/i)).toHaveValue("app-1");
      expect(screen.getByLabelText(/new app secret/i)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /^webhook$|^websocket$/i }),
      ).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/signing secret/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/public callback url/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/tunnel token/i)).not.toBeInTheDocument();
    });

    test("offers only the ignore-other-mentions switch — SeaTalk delivers only @mentions", async () => {
      const api = installApi(mockApiClient());
      renderDialog({
        ...seatalkChannel,
        config: { ...seatalkChannel.config, ignore_other_mentions: true },
      } as unknown as typeof telegramResource);

      expect(screen.queryByRole("switch", { name: /only when @mentioned/i })).toBeNull();
      const ignoreOthers = screen.getByRole("switch", { name: /someone else/i });
      expect(ignoreOthers).toBeChecked();

      fireEvent.click(ignoreOthers);
      save();

      await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
      const config = (api.PATCH.mock.calls[0][1] as { body: { config: Record<string, unknown> } })
        .body.config;
      expect(config.ignore_other_mentions).toBe(false);
      expect("require_mention" in config).toBe(false);
    });

    test("rotating the app secret writes its existing ref before the PATCH", async () => {
      const api = installApi(mockApiClient());
      renderDialog(seatalkChannel);

      fireEvent.change(screen.getByLabelText(/new app secret/i), {
        target: { value: "secret-new" },
      });
      save();

      await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(1));
      expect(api.POST).toHaveBeenCalledWith("/credentials", {
        body: { ref: "channel/st/app-secret", value: "secret-new" },
      });
      await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
      const patchBody = (
        api.PATCH.mock.calls[0][1] as { body: { config: Record<string, unknown> } }
      ).body.config;
      expect(patchBody).toEqual({
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        default_agent: CLAUDE.uid,
      });
    });
  });
});
