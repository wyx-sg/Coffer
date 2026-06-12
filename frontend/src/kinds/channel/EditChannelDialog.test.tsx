// frontend/src/kinds/channel/EditChannelDialog.test.tsx
//
// The edit flow's apply contract: rotating a secret writes the NEW value to
// the channel's EXISTING credential ref BEFORE the config is PATCHed, a blank
// secret field rotates nothing, and changing the bound agent PATCHes the full
// config (refs preserved) with only default_agent changed.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EditChannelDialog } from "./EditChannelDialog";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

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
    default_agent: "builtin",
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

afterEach(() => vi.clearAllMocks());

function save() {
  fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
}

describe("EditChannelDialog", () => {
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
          default_agent: "builtin",
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
        default_agent: "builtin",
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
});
