// src/components/LayoutSetupState.test.tsx — while the daemon waits for git, every page is the setup screen.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { Layout } from "./Layout";

vi.mock("./DaemonOfflineBanner", () => ({
  DaemonStatusBar: () => null,
  DaemonOfflineState: () => null,
}));
vi.mock("./secret/PendingApprovalsSheet", () => ({ PendingApprovalsSheet: () => null }));
vi.mock("./palette/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("./shell/GitSetupState", () => ({
  GitSetupState: ({ setup }: { setup: { reason: string } }) => (
    <div data-testid="git-setup" data-reason={setup.reason} />
  ),
}));
// Everything but the status probe stays unanswered.
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: () => new Promise(() => {}) }),
}));
const status = vi.hoisted(() => {
  // One answer object per state: the shell's connection driver keys effects
  // on it, so a fresh object per render would loop.
  const answer = (value: "setup" | "ready") => ({
    isError: false,
    error: null,
    errorUpdatedAt: 0,
    dataUpdatedAt: 1,
    refetch: () => Promise.resolve(),
    data: {
      status: value,
      features: { knowledge: false, memory: false, sync: false, models: false },
      setup:
        value === "setup"
          ? {
              need: "git",
              reason: "git_missing",
              found: null,
              needed: "2.40",
              message: "Coffer needs git.",
              handoff: { prompt: "Please install git on this machine." },
            }
          : null,
    },
  });
  return {
    value: "setup" as "setup" | "ready",
    answers: { setup: answer("setup"), ready: answer("ready") },
  };
});
vi.mock("@/lib/hooks/useDaemon", async (orig) => ({
  ...(await orig<typeof import("@/lib/hooks/useDaemon")>()),
  useDaemonStatus: () => status.answers[status.value],
}));

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/skills"]}>
        <Routes>
          <Route
            path="*"
            element={
              <Layout
                pageRoutes={[{ path: "*", element: <div>page body</div> }]}
                settingsRoutes={[]}
              />
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Layout while the daemon waits for git", () => {
  test("the setup screen takes the page's place and the sidebar stays", () => {
    status.value = "setup";
    renderShell();
    expect(screen.getByTestId("git-setup")).toHaveAttribute("data-reason", "git_missing");
    expect(screen.queryByText("page body")).toBeNull();
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
  });

  test("a ready daemon shows the page", () => {
    status.value = "ready";
    renderShell();
    expect(screen.getByText("page body")).toBeInTheDocument();
    expect(screen.queryByTestId("git-setup")).toBeNull();
  });
});
