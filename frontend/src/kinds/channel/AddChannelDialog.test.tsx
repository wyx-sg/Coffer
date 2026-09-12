// frontend/src/kinds/channel/AddChannelDialog.test.tsx
//
// The registration flow's ordering contract (mirrors AddMcpServerDialog's
// test): secrets are written to the credential store BEFORE the resource is
// registered (registration probes the refs), and a failed registration rolls
// the just-written secrets back so nothing orphaned stays behind. Channels
// carry no activation scope (ADR per-agent-resource-scope) and no machine affinity, so registration
// is the whole flow — there is no follow-up bind.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AddChannelDialog } from "./AddChannelDialog";
import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
// The model fields read the bound agent's catalogue (spec channels FR-071).
vi.mock("@/lib/api/agentModels", () => ({ agentModelsApi: { list: vi.fn() } }));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);
const { agentModelsApi } = await import("@/lib/api/agentModels");
const listModelsMock = vi.mocked(agentModelsApi.list);

function installApi(api: ApiClientMock) {
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

function renderDialog() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AddChannelDialog open onOpenChange={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function fillTelegram() {
  fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "tg" } });
  fireEvent.change(screen.getByLabelText(/bot token/i), { target: { value: "123:abc" } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /^add channel$/i }));
}

beforeEach(() => {
  listModelsMock.mockResolvedValue({
    models: [
      { id: "claude-opus-5", label: "Opus 5", description: "" },
      { id: "claude-haiku-4-5", label: "Haiku 4.5", description: "" },
    ],
  });
});

afterEach(() => vi.clearAllMocks());

acceptance("channels", "register a telegram channel", async () => {
  const api = installApi(mockApiClient());
  renderDialog();
  fillTelegram();
  submit();

  await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(2));
  // Secret write first (registration probes the credential ref) …
  expect(api.POST.mock.calls[0]).toEqual([
    "/credentials",
    { body: { ref: "channel/tg/bot-token", value: "123:abc" } },
  ]);
  // … then the resource registration with refs only (never the secret).
  expect(api.POST.mock.calls[1]).toEqual([
    "/resources",
    {
      body: {
        kind: "channel",
        name: "tg",
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          default_agent: "claude_code",
        },
      },
    },
  ]);
  expect(api.DELETE).not.toHaveBeenCalled();
});

describe("AddChannelDialog", () => {
  test("seatalk requires all three secrets before anything is written", async () => {
    const api = installApi(mockApiClient());
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: /seatalk/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "st" } });
    fireEvent.change(screen.getByLabelText(/app id/i), { target: { value: "app-1" } });
    // app_secret + signing_secret intentionally left blank.
    submit();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(api.POST).not.toHaveBeenCalled();
  });

  test("seatalk happy path writes both secrets, then registers with refs", async () => {
    const api = installApi(mockApiClient());
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: /seatalk/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "st" } });
    fireEvent.change(screen.getByLabelText(/app id/i), { target: { value: "app-1" } });
    fireEvent.change(screen.getByLabelText(/app secret/i), { target: { value: "s1" } });
    fireEvent.change(screen.getByLabelText(/signing secret/i), { target: { value: "s2" } });
    submit();

    await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(3));
    expect(api.POST.mock.calls.map((c) => c[0])).toEqual([
      "/credentials",
      "/credentials",
      "/resources",
    ]);
    expect(api.POST.mock.calls[2][1]).toEqual({
      body: {
        kind: "channel",
        name: "st",
        config: {
          channel_type: "seatalk",
          app_id: "app-1",
          app_secret_ref: "channel/st/app-secret",
          signing_secret_ref: "channel/st/signing-secret",
          default_agent: "claude_code",
        },
      },
    });
  });

  test("rolls back the written secrets when registration fails", async () => {
    const api = installApi(
      mockApiClient({
        POST: vi.fn(async (path: string) =>
          path === "/resources"
            ? { error: { error: { code: "CONFIG_INVALID", message: "bad config" } } }
            : { data: undefined, error: undefined },
        ) as ApiClientMock["POST"],
      }),
    );
    renderDialog();
    fillTelegram();
    submit();

    await waitFor(() => expect(api.DELETE).toHaveBeenCalledTimes(1));
    expect(api.DELETE).toHaveBeenCalledWith("/credentials/{ref}", {
      params: { path: { ref: "channel/tg/bot-token" } },
    });
    // The translated error surfaces in the dialog.
    expect(await screen.findByRole("alert")).toHaveTextContent(/configuration is invalid/i);
  });

  test("the channel's default model and allowed range reach the registered config", async () => {
    // Curation is the CHANNEL's, not the agent's (spec channels FR-071): a
    // channel has an audience and an agent does not.
    const api = installApi(mockApiClient());
    renderDialog();
    fillTelegram();

    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(2));
    fireEvent.click(screen.getByRole("checkbox", { name: "claude-opus-5" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "claude-haiku-4-5" }));
    const trigger = screen.getByRole("combobox", { name: /default model/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "claude-haiku-4-5" }));
    submit();

    await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(2));
    expect(api.POST.mock.calls[1][1]).toEqual({
      body: {
        kind: "channel",
        name: "tg",
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          default_agent: "claude_code",
          default_model: "claude-haiku-4-5",
          models: ["claude-opus-5", "claude-haiku-4-5"],
        },
      },
    });
  });

  test("an unconfigured channel registers neither curation key", async () => {
    // Nothing ticked = no restriction, and the stored config says nothing
    // rather than carrying an empty list.
    const api = installApi(mockApiClient());
    renderDialog();
    fillTelegram();
    submit();

    await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(2));
    const config = (api.POST.mock.calls[1][1] as { body: { config: Record<string, unknown> } }).body
      .config;
    expect(config).not.toHaveProperty("models");
    expect(config).not.toHaveProperty("default_model");
  });
});
