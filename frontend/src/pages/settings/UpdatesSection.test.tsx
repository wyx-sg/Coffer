// frontend/src/pages/settings/UpdatesSection.test.tsx
//
// Settings › About's update check, against a stand-in for the desktop shell.
// The shell owns the check and the install; what is asserted here is that the
// tab renders the shell's record faithfully and asks it to act. In a browser
// the tab hands the upgrade to an agent with the daemon's prompt.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import type { UpdateStatus } from "@/lib/shellUpdates";

const shell = vi.hoisted(() => ({
  inShell: true,
  status: null as unknown as UpdateStatus,
  listener: null as ((s: UpdateStatus) => void) | null,
  check: vi.fn(),
  install: vi.fn(),
  setAuto: vi.fn(),
}));

vi.mock("@/lib/shellUpdates", () => ({
  updatesAvailable: () => shell.inShell,
  getUpdateStatus: () => Promise.resolve(shell.status),
  checkForUpdates: () => shell.check(),
  installUpdate: () => shell.install(),
  setUpdateAutoCheck: (enabled: boolean) => shell.setAuto(enabled),
  saveAutoCheckPreference: () => {},
  onUpdateStatus: (cb: (s: UpdateStatus) => void) => {
    shell.listener = cb;
    return () => {
      shell.listener = null;
    };
  },
}));

const getMock = vi.fn();
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: getMock }),
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));

const UPGRADE_PROMPT = "Please upgrade Coffer on this machine to the latest release.";

const { UpdatesSection } = await import("./UpdatesSection");

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UpdatesSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Press "Check for updates". The button is on screen, disabled, before the
 * shell has answered with its record, and a press then does nothing — so wait
 * for it to be enabled rather than for it to exist. */
async function pressCheck() {
  const button = await screen.findByRole("button", { name: /check for updates/i });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

const CHECKED_AT = new Date(2026, 8, 30, 9, 15, 0).getTime();

function record(over: Partial<UpdateStatus> = {}): UpdateStatus {
  return {
    configured: true,
    currentVersion: "1.0.0",
    phase: "upToDate",
    lastCheckedAt: CHECKED_AT,
    available: null,
    error: null,
    downloaded: null,
    total: null,
    autoCheck: true,
    ...over,
  };
}

const NEWER = { version: "1.0.1", notes: "- Secrets have their own page.", date: null };

describe("UpdatesSection", () => {
  beforeEach(() => {
    shell.inShell = true;
    shell.status = record();
    shell.listener = null;
    shell.check.mockReset();
    shell.install.mockReset();
    shell.setAuto.mockReset();
    getMock.mockReset();
    getMock.mockResolvedValue({
      data: { install_method: "binaries", handoff: { prompt: UPGRADE_PROMPT } },
    });
  });

  acceptance("web-ui", "about shows the version and when updates were last checked", async () => {
    renderSection();
    expect(await screen.findByText("Coffer is up to date")).toBeInTheDocument();
    expect(screen.getByText(/Last checked 2026-09-30 09:15:00/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /check for updates/i })).toBeEnabled();
    expect(screen.getByRole("switch", { name: /check automatically/i })).toBeChecked();
  });

  acceptance("web-ui", "checking by hand finds a newer version", async () => {
    const later = CHECKED_AT + 60_000;
    shell.check.mockImplementation(() => {
      // The shell announces the check running, then answers with what it found.
      shell.listener?.(record({ phase: "checking" }));
      return Promise.resolve(
        record({ phase: "available", available: NEWER, lastCheckedAt: later }),
      );
    });
    renderSection();
    await pressCheck();
    expect(shell.check).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Coffer 1.0.1 is available")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download and restart/i })).toBeEnabled();
    expect(screen.getByText(/2026-09-30 09:16:00/)).toBeInTheDocument();
    expect(screen.getByText("Secrets have their own page.")).toBeInTheDocument();
  });

  test("a busy check takes no second press", async () => {
    shell.status = record({ phase: "checking" });
    renderSection();
    const busy = await screen.findByRole("button", { name: /checking/i });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    await waitFor(() => expect(shell.check).not.toHaveBeenCalled());
  });

  acceptance("web-ui", "download and restart installs the newer version", async () => {
    shell.status = record({ phase: "available", available: NEWER });
    shell.install.mockReturnValue(new Promise(() => {})); // relaunches: never settles
    renderSection();
    fireEvent.click(await screen.findByRole("button", { name: /download and restart/i }));
    expect(shell.install).toHaveBeenCalledTimes(1);
    act(() =>
      shell.listener?.(
        record({ phase: "downloading", available: NEWER, downloaded: 30, total: 120 }),
      ),
    );
    const busy = await screen.findByRole("button", { name: /downloading… 25%/i });
    expect(busy).toBeDisabled();
  });

  acceptance("web-ui", "a failed check keeps the last good result", async () => {
    shell.check.mockResolvedValue(
      record({
        phase: "failed",
        error: "Couldn't reach the release manifest on github.com (timed out).",
      }),
    );
    renderSection();
    await pressCheck();
    expect(await screen.findByText("Couldn't check for updates")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/timed out.*You are on 1\.0\.0/);
    // The last successful check's time is still the one shown.
    expect(screen.getByText(/Last checked 2026-09-30 09:15:00/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeEnabled();
  });

  acceptance("web-ui", "about in a browser offers no update control", async () => {
    shell.inShell = false;
    renderSection();
    expect(screen.getByText(/installed by the Coffer desktop app/)).toBeInTheDocument();
    // The upgrade goes to an agent: Copy prompt, and nothing that installs.
    expect(await screen.findByRole("button", { name: /copy prompt/i })).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("/daemon/upgrade");
    expect(screen.queryByRole("button", { name: /check for updates/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  test("the desktop shell never asks for the upgrade hand-off", async () => {
    renderSection();
    expect(await screen.findByText("Coffer is up to date")).toBeInTheDocument();
    expect(getMock).not.toHaveBeenCalled();
  });
});
