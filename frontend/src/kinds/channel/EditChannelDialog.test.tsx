// frontend/src/kinds/channel/EditChannelDialog.test.tsx
//
// The edit flow's apply contract: rotating a secret writes the NEW value to
// the channel's EXISTING credential ref BEFORE the config is PATCHed, a blank
// secret field rotates nothing, and changing the bound agent PATCHes the full
// config (refs preserved) with only default_agent changed.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EditChannelDialog } from "./EditChannelDialog";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
// The agent picker reads the turn platform's provider registry
// (GET /agent-providers) — the same registry a turn resolves by — so it can
// only offer real provider keys.
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
// The model fields read the BOUND agent's catalogue (spec channels FR-071).
vi.mock("@/lib/api/agentModels", () => ({ agentModelsApi: { list: vi.fn() } }));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgentsMock = vi.mocked(agentProvidersApi.list);
const { agentModelsApi } = await import("@/lib/api/agentModels");
const listModelsMock = vi.mocked(agentModelsApi.list);

function installApi(api: ApiClientMock) {
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

const telegramResource = {
  ref: "channel:tg",
  kind: "channel",
  name: "tg",
  enabled: true,
  config: {
    channel_type: "telegram",
    bot_token_ref: "channel/tg/bot-token",
    default_agent: "claude_code",
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
  listAgentsMock.mockResolvedValue({
    agents: [
      { agent_key: "claude_code", display_name: "Claude Code", available: true },
      { agent_key: "codex", display_name: "Codex", available: true },
    ],
  });
  listModelsMock.mockImplementation(async (agentKey: string) => ({
    models:
      agentKey === "codex"
        ? [{ id: "gpt-5-codex", label: "", description: "" }]
        : [
            { id: "claude-opus-5", label: "Opus 5", description: "" },
            { id: "claude-haiku-4-5", label: "Haiku 4.5", description: "" },
          ],
  }));
});

afterEach(() => vi.clearAllMocks());

function save() {
  fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
}

describe("EditChannelDialog", () => {
  test("sources the agent picker from the chat provider registry, not the resource list", async () => {
    // The bound agent is a chat provider key (claude_code, underscore). The
    // picker must read the same registry the turn resolves by (agentProvidersApi.list
    // → GET /chat/agents) so a re-bind can only ever pick a real provider key.
    // The old useAgents() source served resource names (claude-code), which
    // fail at turn time with UNKNOWN_AGENT.
    installApi(mockApiClient());
    renderDialog();

    await waitFor(() => expect(listAgentsMock).toHaveBeenCalled());
  });

  test("rotating the bot token writes the existing ref first, then PATCHes config", async () => {
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
    expect(api.PATCH).toHaveBeenCalledWith("/resources/{kind}/{name}", {
      params: { path: { kind: "channel", name: "tg" } },
      body: {
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          default_agent: "claude_code",
        },
      },
    });
  });

  test("a blank token rotates nothing — only the config PATCH runs", async () => {
    const api = installApi(mockApiClient());
    renderDialog();
    save();

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(api.POST).not.toHaveBeenCalled();
  });

  test("seatalk: rotating the signing secret writes its existing ref before the PATCH", async () => {
    const api = installApi(mockApiClient());
    renderDialog({
      kind: "channel",
      name: "st",
      enabled: true,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: "claude_code",
      },
    } as unknown as typeof telegramResource);

    fireEvent.change(screen.getByLabelText(/new signing secret/i), {
      target: { value: "sig-new" },
    });
    save();

    await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(1));
    expect(api.POST).toHaveBeenCalledWith("/credentials", {
      body: { ref: "channel/st/signing-secret", value: "sig-new" },
    });
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    const patchBody = (api.PATCH.mock.calls[0][1] as { body: { config: Record<string, unknown> } })
      .body.config;
    expect(patchBody.app_secret_ref).toBe("channel/st/app-secret");
    expect(patchBody.signing_secret_ref).toBe("channel/st/signing-secret");
  });

  // --- the channel's own model curation (spec channels FR-071) --------------

  test("the stored default model and allowed range load, and an edit rides the PATCH", async () => {
    const api = installApi(mockApiClient());
    renderDialog({
      kind: "channel",
      name: "tg",
      enabled: true,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: "claude_code",
        default_model: "claude-opus-5",
        models: ["claude-opus-5"],
      },
    } as unknown as typeof telegramResource);

    // The stored range arrives ticked, and the pinned model is shown.
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "claude-opus-5" })).toBeChecked(),
    );
    expect(screen.getByRole("combobox", { name: /default model/i })).toHaveTextContent(
      "claude-opus-5",
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "claude-haiku-4-5" }));
    save();

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(api.PATCH).toHaveBeenCalledWith("/resources/{kind}/{name}", {
      params: { path: { kind: "channel", name: "tg" } },
      body: {
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          default_agent: "claude_code",
          default_model: "claude-opus-5",
          models: ["claude-opus-5", "claude-haiku-4-5"],
        },
      },
    });
  });

  test("emptying the range lifts the restriction and leaves the pinned model alone", async () => {
    const api = installApi(mockApiClient());
    renderDialog({
      kind: "channel",
      name: "tg",
      enabled: true,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: "claude_code",
        default_model: "claude-opus-5",
        models: ["claude-opus-5"],
      },
    } as unknown as typeof telegramResource);

    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "claude-opus-5" })).toBeChecked(),
    );
    // Un-ticking the last entry removes the RANGE, not the pin: with nothing
    // curated there is no range to be outside of, so the channel keeps opening
    // on the model the user chose while allowing anything the agent offers.
    fireEvent.click(screen.getByRole("checkbox", { name: "claude-opus-5" }));
    save();

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(api.PATCH).toHaveBeenCalledWith("/resources/{kind}/{name}", {
      params: { path: { kind: "channel", name: "tg" } },
      body: {
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          default_agent: "claude_code",
          default_model: "claude-opus-5",
        },
      },
    });
  });

  test("re-binding the agent drops the old agent's model ids instead of submitting them", async () => {
    const api = installApi(mockApiClient());
    renderDialog({
      kind: "channel",
      name: "tg",
      enabled: true,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: "claude_code",
        default_model: "claude-opus-5",
        models: ["claude-opus-5"],
      },
    } as unknown as typeof telegramResource);

    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "claude-opus-5" })).toBeChecked(),
    );
    const agentTrigger = screen.getByRole("combobox", { name: /default agent/i });
    fireEvent.keyDown(agentTrigger, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "Codex" }));
    save();

    // A Claude id on a Codex channel would be handed to the CLI verbatim.
    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    expect(api.PATCH).toHaveBeenCalledWith("/resources/{kind}/{name}", {
      params: { path: { kind: "channel", name: "tg" } },
      body: {
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          default_agent: "codex",
        },
      },
    });
  });
});
