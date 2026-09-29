// frontend/src/pages/settings/UpdatesSection.test.tsx
//
// Settings › About's update check, against a stand-in for the desktop shell.
// The shell owns the check and the install; what is asserted here is that the
// tab renders the shell's record faithfully and asks it to act.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

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

const { UpdatesSection } = await import("./UpdatesSection");

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
  });

  acceptance("web-ui", "about shows the version and when updates were last checked", async () => {
    render(<UpdatesSection />);
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
    render(<UpdatesSection />);
    fireEvent.click(await screen.findByRole("button", { name: /check for updates/i }));
    expect(shell.check).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Coffer 1.0.1 is available")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download and restart/i })).toBeEnabled();
    expect(screen.getByText(/2026-09-30 09:16:00/)).toBeInTheDocument();
    expect(screen.getByText("Secrets have their own page.")).toBeInTheDocument();
  });

  test("a busy check takes no second press", async () => {
    shell.status = record({ phase: "checking" });
    render(<UpdatesSection />);
    const busy = await screen.findByRole("button", { name: /checking/i });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    await waitFor(() => expect(shell.check).not.toHaveBeenCalled());
  });

  acceptance("web-ui", "download and restart installs the newer version", async () => {
    shell.status = record({ phase: "available", available: NEWER });
    shell.install.mockReturnValue(new Promise(() => {})); // relaunches: never settles
    render(<UpdatesSection />);
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
    render(<UpdatesSection />);
    fireEvent.click(await screen.findByRole("button", { name: /check for updates/i }));
    expect(await screen.findByText("Couldn't check for updates")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/timed out.*You are on 1\.0\.0/);
    // The last successful check's time is still the one shown.
    expect(screen.getByText(/Last checked 2026-09-30 09:15:00/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeEnabled();
  });

  acceptance("web-ui", "about in a browser offers no update control", () => {
    shell.inShell = false;
    render(<UpdatesSection />);
    expect(screen.getByText(/installed by the Coffer desktop app/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });
});
