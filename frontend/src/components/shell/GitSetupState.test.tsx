// src/components/shell/GitSetupState.test.tsx — the setup screen while the daemon waits for git (board 1.1.22).
import { afterEach, beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { DaemonSetup } from "@/lib/api/daemon";
import { acceptance } from "@/test/acceptance";
import { GitSetupState } from "./GitSetupState";

const setupCheck = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/daemon", async (orig) => {
  const real = await orig<typeof import("@/lib/api/daemon")>();
  return { ...real, daemonApi: { ...real.daemonApi, setupCheck } };
});
// A browser: the daemon restarts itself and the page reloads from it.
const restartFromBrowser = vi.hoisted(() => vi.fn(() => new Promise<void>(() => {})));
vi.mock("@/lib/daemonRestart", async (orig) => ({
  ...(await orig<typeof import("@/lib/daemonRestart")>()),
  restartFromBrowser,
}));
vi.mock("@/lib/tauri", async (orig) => ({
  ...(await orig<typeof import("@/lib/tauri")>()),
  inDesktopShell: () => false,
}));
// In the setup state no managed agent answers, so the hand-off is Copy prompt.
vi.mock("@/lib/hooks/useAgentProviders", () => ({ useAgentProviders: () => ({ data: [] }) }));

const MISSING: DaemonSetup = {
  need: "git",
  reason: "git_missing",
  found: null,
  needed: "2.40",
  message: "Coffer needs git, and git isn't installed on this machine.",
  handoff: { prompt: "Please install git on this machine." },
};
const TOO_OLD: DaemonSetup = {
  ...MISSING,
  reason: "git_too_old",
  found: "2.30",
  handoff: { prompt: "Please update git on this machine to version 2.40 or later." },
};

function renderScreen(setup: DaemonSetup) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Routes>
          <Route path="*" element={<GitSetupState setup={setup} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const writeText = vi.fn(() => Promise.resolve());

beforeEach(() => {
  setupCheck.mockReset();
  restartFromBrowser.mockClear();
  writeText.mockClear();
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
});
afterEach(() => {
  delete (navigator as unknown as { clipboard?: unknown }).clipboard;
});

describe("GitSetupState", () => {
  acceptance(
    "web-ui",
    "the setup screen says git is missing and hands the install to an agent",
    async () => {
      renderScreen(MISSING);
      const screenEl = screen.getByTestId("git-setup");
      expect(screen.getByRole("heading", { name: "Coffer needs git" })).toBeInTheDocument();
      expect(screenEl).toHaveTextContent("git isn’t installed on this machine.");
      expect(screenEl).toHaveTextContent("The vault keeps its history and syncs with git.");
      expect(screen.getByTestId("git-check-again")).toHaveTextContent("Check again");
      fireEvent.click(screen.getByRole("button", { name: /copy prompt/i }));
      await waitFor(() => expect(writeText).toHaveBeenCalledWith(MISSING.handoff.prompt));
    },
  );

  acceptance("web-ui", "the setup screen names the version that is too old", () => {
    renderScreen(TOO_OLD);
    expect(screen.getByTestId("git-setup")).toHaveTextContent(
      "git 2.30 is older than 2.40, which Coffer needs.",
    );
  });

  acceptance("web-ui", "check again restarts the daemon once git is there", async () => {
    setupCheck.mockResolvedValueOnce({ ready: false, setup: MISSING });
    renderScreen(MISSING);
    fireEvent.click(screen.getByTestId("git-check-again"));
    expect(await screen.findByText(/Still not found · checked/)).toBeInTheDocument();
    expect(restartFromBrowser).not.toHaveBeenCalled();

    setupCheck.mockResolvedValueOnce({ ready: true, setup: null });
    fireEvent.click(screen.getByTestId("git-check-again"));
    await waitFor(() => expect(restartFromBrowser).toHaveBeenCalledOnce());
    expect(screen.getByTestId("git-check-again")).toHaveTextContent("Starting Coffer…");
  });
});
