// frontend/src/pages/settings/DaemonSettings.test.tsx — Settings → Daemon: status, the host's restart, Start at login and the port.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import { DaemonSettings } from "./DaemonSettings";

const shell = vi.hoisted(() => ({ inShell: false }));
vi.mock("@/lib/tauri", async (orig) => ({
  ...(await orig<typeof import("@/lib/tauri")>()),
  isTauri: () => shell.inShell,
  inDesktopShell: () => shell.inShell,
  daemonVersionMatches: async () => true,
  restartDaemon: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn(), resetApiClient: vi.fn() }));
// The browser's restart (the daemon restarts itself, then the page reloads) is
// lib/daemonRestart.test.ts; here it only has to be the one the button runs.
const browserRestart = vi.hoisted(() => vi.fn(() => new Promise<void>(() => {})));
vi.mock("@/lib/daemonRestart", async (orig) => ({
  ...(await orig<typeof import("@/lib/daemonRestart")>()),
  restartFromBrowser: browserRestart,
}));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

const STATUS = {
  status: "ready",
  port: 8000,
  version: "0.4.2",
  channel: "stable",
  started_at: "2026-09-27T10:00:00Z",
  executable: "/Users/u/.coffer/bin/coffer-daemon",
  machine_id: null,
  machine_name: "mac",
  features: {},
  upstream_summary: null,
  pid: 51233,
  commit: null,
  data_dir: "~/.coffer",
  connected_agents: 2,
};

type Answer = { data?: unknown; error?: unknown };

function mockApi({
  status = { data: STATUS } as Answer | "pending",
  port = { port: 8000, bound_port: 8000, pending: false },
  put = vi.fn(
    async (path: string, { body }: { body: { port: number } }): Promise<Answer> =>
      path === "/daemon/port"
        ? { data: { port: body.port, bound_port: 8000, pending: body.port !== 8000 } }
        : { data: { login_service_supported: true, login_service_installed: false } },
  ),
} = {}) {
  const get = vi.fn(async (path: string): Promise<Answer> => {
    if (path === "/daemon/status") {
      if (status === "pending") return new Promise(() => {});
      return status;
    }
    if (path === "/daemon/port") return { data: port };
    return { data: { login_service_supported: true, login_service_installed: false } };
  });
  getApiClientMock.mockReturnValue({ GET: get, PUT: put } as unknown as ReturnType<
    typeof getApiClient
  >);
  return { get, put };
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <DaemonSettings />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("DaemonSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    shell.inShell = false;
  });

  acceptance("web-ui", "the settings daemon tab shows the running daemon", async () => {
    mockApi();
    renderTab();
    const card = await screen.findByTestId("settings-daemon-status");
    expect(within(card).getByText("Running on 127.0.0.1:8000")).toBeInTheDocument();
    expect(within(card).getByTestId("settings-daemon-status-line")).toHaveTextContent(
      /^Up \d+ days? · pid 51233 · 2 agents connected$/,
    );
    expect(screen.queryByRole("button", { name: /stop|shut ?down/i })).toBeNull();
  });

  acceptance("web-ui", "the settings daemon tab offers the host's restart", async () => {
    mockApi();
    const { unmount } = renderTab();
    const card = await screen.findByTestId("settings-daemon-status");
    expect(within(card).queryByText("coffer daemon restart")).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: /^restart$/i }));
    await waitFor(() => expect(browserRestart).toHaveBeenCalledTimes(1));
    unmount();

    shell.inShell = true;
    renderTab();
    const shellCard = await screen.findByTestId("settings-daemon-status");
    expect(within(shellCard).queryByText("coffer daemon restart")).toBeNull();
    // In the desktop shell the same control runs the shell's restart.
    const { restartDaemon } = await import("@/lib/tauri");
    vi.mocked(restartDaemon).mockReturnValue(new Promise(() => {}));
    fireEvent.click(within(shellCard).getByRole("button", { name: /^restart$/i }));
    await waitFor(() => expect(restartDaemon).toHaveBeenCalledTimes(1));
    expect(browserRestart).toHaveBeenCalledTimes(1);
  });

  acceptance("web-ui", "saving a valid port leaves it pending until restart", async () => {
    shell.inShell = true;
    const { put } = mockApi();
    renderTab();
    const field = await screen.findByRole("textbox", { name: /^port$/i });
    await waitFor(() => expect(field).toHaveValue("8000"));
    fireEvent.change(field, { target: { value: "8123" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/daemon/port", { body: { port: 8123 } }));
    const pending = await screen.findByTestId("settings-daemon-port-pending");
    expect(
      within(pending).getByText(/port 8123 saved — takes effect after coffer restarts/i),
    ).toBeInTheDocument();
    expect(within(pending).getByRole("button", { name: /restart now/i })).toBeInTheDocument();
    expect(screen.getByText("Running on 127.0.0.1:8000")).toBeInTheDocument();
  });

  test("in a browser the pending port offers Restart now too", async () => {
    mockApi({ port: { port: 8123, bound_port: 8000, pending: true } });
    renderTab();
    const pending = await screen.findByTestId("settings-daemon-port-pending");
    expect(within(pending).queryByText("coffer daemon restart")).toBeNull();
    fireEvent.click(within(pending).getByRole("button", { name: /restart now/i }));
    await waitFor(() => expect(browserRestart).toHaveBeenCalledTimes(1));
  });

  acceptance("web-ui", "a port in use is rejected", async () => {
    const put = vi.fn(
      async (): Promise<Answer> => ({
        error: {
          error: {
            code: "PORT_IN_USE",
            message: "port 9000 is in use by node (pid 4242)",
            details: { port: 9000, holder: { pid: 4242, name: "node", command: "node server.js" } },
          },
        },
      }),
    );
    mockApi({ put });
    renderTab();
    const field = await screen.findByRole("textbox", { name: /^port$/i });
    await waitFor(() => expect(field).toHaveValue("8000"));
    fireEvent.change(field, { target: { value: "9000" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(
      await screen.findByText("Port 9000 is in use by node (pid 4242). Pick another port."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("settings-daemon-port-pending")).toBeNull();
    // Save stays disabled while the refusal is shown, until the port is edited.
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();

    fireEvent.change(field, { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText("Use a port from 1024 to 65535.")).toBeInTheDocument();
    expect(put).toHaveBeenCalledTimes(1);
  });

  acceptance(
    "web-ui",
    "the daemon tab has no token row and no troubleshooting section",
    async () => {
      mockApi();
      renderTab();
      await screen.findByTestId("settings-daemon-status");
      expect(screen.queryByText(/token/i)).toBeNull();
      expect(screen.queryByText(/troubleshoot/i)).toBeNull();
      expect(screen.queryByText(/copy diagnostics/i)).toBeNull();
      expect(screen.queryByText(/daemon log/i)).toBeNull();
    },
  );

  acceptance("web-ui", "the settings daemon tab keeps its layout while status loads", () => {
    mockApi({ status: "pending" });
    renderTab();
    expect(screen.getByTestId("settings-daemon-status-loading")).toBeInTheDocument();
    expect(screen.getByTestId("settings-daemon-startup")).toBeInTheDocument();
    expect(screen.queryByText(/offline/i)).toBeNull();
  });

  acceptance("web-ui", "the settings daemon tab with the daemon offline", async () => {
    mockApi({
      status: { error: { error: { code: "DAEMON_NOT_READY", message: "down", details: {} } } },
    });
    renderTab();
    expect(await screen.findByText(/offline — the daemon isn't answering/i)).toBeInTheDocument();
    expect(screen.getByText("coffer daemon start")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /start at login/i })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: /^port$/i })).toBeDisabled();
  });
});
