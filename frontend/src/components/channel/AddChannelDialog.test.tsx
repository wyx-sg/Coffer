// frontend/src/components/channel/AddChannelDialog.test.tsx
//
// The registration flow's ordering contract (mirrors AddMcpServerDialog's
// test): secrets are written to the credential store BEFORE the resource is
// registered (registration probes the refs), and a failed registration rolls
// the just-written secrets back so nothing orphaned stays behind.
//
// Registration is still the whole flow — there is no follow-up bind request —
// but the config it writes now names a machine: `runs_on` is this machine's
// id, read off `GET /sync/status`, so a channel created here is answered here
// instead of sitting unbound and never starting.
//
// It also names an AGENT, and that is why this suite seeds an agent list. The
// config's `default_agent` used to be a constant every install shared (the
// chat provider key `claude_code`); it holds an agent RESOURCE UID now, minted
// per vault, so there is nothing for the form to assume and it asks. The uids
// below are spelled nothing like the agents' names on purpose: the config
// carries the uid, the picker shows the name, and an assertion that could be
// satisfied by either string would prove neither.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AddChannelDialog } from "./AddChannelDialog";
import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
// The dialog binds the new channel to this machine, so it reads the daemon's
// machine id. Stubbed rather than served, since nothing else here needs a daemon.
vi.mock("@/lib/hooks/useMachines", () => ({ useThisMachineId: vi.fn() }));
// The agent picker (AgentSelect) reads the registered agents. Stubbed for the
// same reason: `agentsApi.list` goes out through `call`, not the api client
// mocked above, and what this suite is about is what the form SENDS.
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));
const navigateMock = vi.fn();
vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);
const { useThisMachineId } = await import("@/lib/hooks/useMachines");
const useThisMachineIdMock = vi.mocked(useThisMachineId);
const { useAgents } = await import("@/lib/hooks/useAgents");
const useAgentsMock = vi.mocked(useAgents);

/** This machine's id, as the daemon reports it. */
const HERE = "machine-here";

/** The registered agents — opaque uids, readable names. The form opens on the
 *  first of them, so `CLAUDE.uid` is what an unattended submit sends. */
const CLAUDE = { uid: "u-6c1d0b83", name: "claude-code" };
const CODEX = { uid: "u-f04a927e", name: "codex" };

/** The uid the daemon mints for the new channel — the dialog navigates to it. */
const NEW_UID = "u-2e7b5aa1";

function stubMachineId(machineId: string | null) {
  useThisMachineIdMock.mockReturnValue({ machineId, isPending: false });
}

function stubAgents(agents: { uid: string; name: string }[]) {
  useAgentsMock.mockReturnValue({ data: agents } as unknown as ReturnType<typeof useAgents>);
}

/**
 * The api client, with `POST /resources` answering the way the daemon does:
 * the row it created, uid and all. The dialog needs the uid for the link and
 * the name for the toast, so a stub that answered with neither would make
 * every registration here look like a failure and trigger the rollback.
 */
function installApi(api: ApiClientMock) {
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

function registeringApi(overrides: Partial<ApiClientMock> = {}) {
  return installApi(
    mockApiClient({
      POST: vi.fn(async (path: string, init?: unknown) =>
        path === "/resources"
          ? {
              data: {
                uid: NEW_UID,
                ...(init as { body: Record<string, unknown> }).body,
                enabled: true,
              },
            }
          : { data: undefined, error: undefined },
      ) as ApiClientMock["POST"],
      ...overrides,
    }),
  );
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

/**
 * The ref of the n-th `/credentials` write, read back off the mock.
 *
 * A ref is minted opaque — `channel/<uuid4 hex>/<secret>` — so no test can name
 * the value it expects, and the thing worth asserting was never the value: it
 * is that the secret write and the config that follows it agree on ONE address.
 * Reading it back and reusing it is what makes that agreement the assertion
 * rather than two independent guesses.
 */
function writtenRef(api: ApiClientMock, nth: number): string {
  const call = api.POST.mock.calls.filter((c) => c[0] === "/credentials")[nth];
  return (call[1] as { body: { ref: string } }).body.ref;
}

/** The shape itself, where the pairing above is not what is under test. */
const refFor = (secret: string) =>
  expect.stringMatching(new RegExp(`^channel/[0-9a-f]{32}/${secret}$`));

beforeEach(() => {
  stubMachineId(HERE);
  stubAgents([CLAUDE, CODEX]);
});
afterEach(() => vi.clearAllMocks());

acceptance("channels", "register a telegram channel", async () => {
  const api = registeringApi();
  renderDialog();
  fillTelegram();
  submit();

  await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(2));
  // Secret write first (registration probes the credential ref) …
  expect(api.POST.mock.calls[0]).toEqual([
    "/credentials",
    { body: { ref: refFor("bot-token"), value: "123:abc" } },
  ]);
  // … then the resource registration with refs only (never the secret), citing
  // the very address the write above used.
  expect(api.POST.mock.calls[1]).toEqual([
    "/resources",
    {
      body: {
        kind: "channel",
        name: "tg",
        config: {
          channel_type: "telegram",
          bot_token_ref: writtenRef(api, 0),
          default_agent: CLAUDE.uid,
          runs_on: HERE,
        },
      },
    },
  ]);
  expect(api.DELETE).not.toHaveBeenCalled();
  // The name is the user's word for the channel; the uid is the daemon's, and
  // it is the one the link is built from.
  expect(navigateMock).toHaveBeenCalledWith(`/channels/${NEW_UID}`);
});

describe("the agent the channel drives", () => {
  test("the picker offers NAMES and the config carries the chosen agent's uid", async () => {
    const api = registeringApi();
    renderDialog();

    // What the list shows is what the owner calls their agents — a uid is the
    // one thing they cannot read, and the form never puts one in front of them.
    const picker = screen.getByRole("combobox", { name: /default agent/i });
    fireEvent.keyDown(picker, { key: "ArrowDown" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      CLAUDE.name,
      CODEX.name,
    ]);

    fireEvent.click(screen.getByRole("option", { name: CODEX.name }));
    fillTelegram();
    submit();

    await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(2));
    expect(
      (api.POST.mock.calls[1][1] as { body: { config: { default_agent: string } } }).body.config
        .default_agent,
    ).toBe(CODEX.uid);
  });

  test("with no agent registered, nothing is written and the form says why", async () => {
    // There is no fallback to fall back TO: the field held a constant every
    // install shared until agents got uids, and a channel bound to nobody is a
    // bot that never answers. So the form refuses rather than inventing one.
    stubAgents([]);
    const api = registeringApi();
    renderDialog();
    fillTelegram();
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(/register an agent first/i);
    expect(api.POST).not.toHaveBeenCalled();
  });
});

describe("AddChannelDialog", () => {
  test("seatalk requires the app id and app secret before anything is written", async () => {
    const api = registeringApi();
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: /seatalk/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "st" } });
    // app_id + app_secret intentionally left blank.
    submit();

    // One translated message under each missing field — never zod's own
    // "String must contain…", and no toast for a validation miss.
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.map((a) => a.textContent)).toEqual(["Enter the App ID", "Enter the App secret"]);
    expect(screen.queryByText(/must contain/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/app secret/i)).toHaveAttribute("aria-invalid", "true");
    expect(api.POST).not.toHaveBeenCalled();
  });

  test("a malformed name is refused under the name field", async () => {
    const api = registeringApi();
    renderDialog();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "my bot!" } });
    fireEvent.change(screen.getByLabelText(/bot token/i), { target: { value: "123:abc" } });
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Letters, digits, dash and underscore only",
    );
    expect(api.POST).not.toHaveBeenCalled();
  });

  acceptance(
    "credentials",
    "a surface lifts a pasted secret into the store before registering",
    async () => {
      const api = registeringApi();
      renderDialog();

      fireEvent.click(screen.getByRole("button", { name: /seatalk/i }));
      fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "st" } });
      fireEvent.change(screen.getByLabelText(/app id/i), { target: { value: "app-1" } });
      fireEvent.change(screen.getByLabelText(/app secret/i), { target: { value: "s1" } });
      submit();

      await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(2));
      expect(api.POST.mock.calls.map((c) => c[0])).toEqual(["/credentials", "/resources"]);
      expect(api.POST.mock.calls[0]).toEqual([
        "/credentials",
        { body: { ref: refFor("app-secret"), value: "s1" } },
      ]);
      expect(api.POST.mock.calls[1][1]).toEqual({
        body: {
          kind: "channel",
          name: "st",
          config: {
            channel_type: "seatalk",
            app_id: "app-1",
            app_secret_ref: writtenRef(api, 0),
            default_agent: CLAUDE.uid,
            runs_on: HERE,
          },
        },
      });
    },
  );

  test("seatalk asks for its app credentials only, and says what Coffer cannot do for the owner", () => {
    installApi(mockApiClient());
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: /seatalk/i }));

    expect(screen.getByLabelText(/app id/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/app secret/i)).toBeInTheDocument();
    // No transport to choose and nothing a webhook needed.
    expect(
      screen.queryByRole("button", { name: /^webhook$|^websocket$/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/signing secret/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/public callback url/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/tunnel token/i)).not.toBeInTheDocument();
    // The SDK and the portal setting are stated on the spot.
    expect(screen.getByText(/~\/\.coffer\/vendor/)).toBeInTheDocument();
    expect(screen.getByText(/Developer Portal/)).toBeInTheDocument();
  });

  test("writes nothing at all while this machine's id is unknown", async () => {
    // Registering anyway would create a channel bound to nobody — a bot that
    // never answers on any machine — so the form says why and stays open.
    stubMachineId(null);
    const api = registeringApi();
    renderDialog();
    fillTelegram();
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(/machine's id/i);
    expect(api.POST).not.toHaveBeenCalled();
  });

  acceptance("credentials", "a failed registration leaves no orphaned credential", async () => {
    const api = registeringApi({
      POST: vi.fn(async (path: string) =>
        path === "/resources"
          ? { error: { error: { code: "CONFIG_INVALID", message: "bad config" } } }
          : { data: undefined, error: undefined },
      ) as ApiClientMock["POST"],
    });
    renderDialog();
    fillTelegram();
    submit();

    await waitFor(() => expect(api.DELETE).toHaveBeenCalledTimes(1));
    // The rollback deletes the address that was just written, whatever it is.
    expect(api.DELETE).toHaveBeenCalledWith("/credentials/{ref}", {
      params: { path: { ref: writtenRef(api, 0) } },
    });
    // The translated error surfaces in the dialog.
    expect(await screen.findByRole("alert")).toHaveTextContent(/configuration is invalid/i);
  });
});
