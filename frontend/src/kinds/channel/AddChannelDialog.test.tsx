// frontend/src/kinds/channel/AddChannelDialog.test.tsx
//
// The registration flow's ordering contract (mirrors AddMcpServerDialog's
// test): secrets are written to the credential store BEFORE the resource is
// registered (registration probes the refs), and a failed registration rolls
// the just-written secrets back so nothing orphaned stays behind.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AddChannelDialog } from "./AddChannelDialog";
import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

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

afterEach(() => vi.clearAllMocks());

acceptance("009-channels", "register a telegram channel", async () => {
  const api = installApi(mockApiClient());
  renderDialog();
  fillTelegram();
  submit();

  await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(2));
  // Secret write first (registration probes the credential ref) …
  expect(api.POST.mock.calls[0]).toEqual([
    "/keychain",
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
          default_agent: "builtin",
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
    expect(api.POST.mock.calls.map((c) => c[0])).toEqual(["/keychain", "/keychain", "/resources"]);
    expect(api.POST.mock.calls[2][1]).toEqual({
      body: {
        kind: "channel",
        name: "st",
        config: {
          channel_type: "seatalk",
          app_id: "app-1",
          app_secret_ref: "channel/st/app-secret",
          signing_secret_ref: "channel/st/signing-secret",
          default_agent: "builtin",
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
    expect(api.DELETE).toHaveBeenCalledWith("/keychain/{ref}", {
      params: { path: { ref: "channel/tg/bot-token" } },
    });
    // The translated error surfaces in the dialog.
    expect(await screen.findByRole("alert")).toHaveTextContent(/configuration is invalid/i);
  });
});
