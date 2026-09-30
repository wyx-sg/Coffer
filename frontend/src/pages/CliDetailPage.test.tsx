// src/pages/CliDetailPage.test.tsx — one command's page: Check again, the login command, the Homebrew confirmation.
//
// Real QueryClientProvider; only the api module is mocked.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { GCLOUD_LOGGED_OUT, JQ_MISSING, UV_READY } from "@/test/cliFixtures";
import { CliDetailPage } from "./CliDetailPage";

vi.mock("@/lib/api/clis", () => ({
  clisApi: {
    list: vi.fn(),
    checkAll: vi.fn(),
    get: vi.fn(),
    check: vi.fn(),
    install: vi.fn(),
    installStatus: vi.fn(),
  },
}));
const { clisApi } = await import("@/lib/api/clis");
const api = vi.mocked(clisApi);

function renderAt(command: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/clis/${command}`]}>
          <Routes>
            <Route path="/clis/:command" element={<CliDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("CliDetailPage", () => {
  // scenario (web-ui, revise-web-ui-ia 7.14d): "check again after logging in"
  test("check again after logging in", async () => {
    api.get.mockResolvedValue(GCLOUD_LOGGED_OUT);
    api.check.mockResolvedValue({
      ...GCLOUD_LOGGED_OUT,
      status: "ready",
      login: { ...GCLOUD_LOGGED_OUT.login, state: "logged_in" },
    });
    renderAt("gcloud");

    const banner = await screen.findByTestId("cli-problem");
    expect(banner).toHaveTextContent("gcloud isn't logged in — 1 skill affected");
    expect(banner).toHaveTextContent("gcloud auth login");
    // The login command is there to copy; Coffer never runs it.
    expect(within(banner).getByRole("button", { name: "Copy command" })).toBeInTheDocument();
    expect(screen.getByText("Run it in a terminal, then press Check again.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Install|Update/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.check).toHaveBeenCalledWith("gcloud"));
    await waitFor(() => expect(screen.queryByTestId("cli-problem")).toBeNull());
    expect(screen.getByText("Logged in")).toBeInTheDocument();
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
  });

  test("a missing command offers Install… behind the confirmation, and names the skills it breaks", async () => {
    api.get.mockResolvedValue(JQ_MISSING);
    renderAt("jq");
    const banner = await screen.findByTestId("cli-problem");
    expect(banner).toHaveTextContent("jq isn't installed — 2 skills affected");
    expect(banner).toHaveTextContent("gh-triage, log-digest will fail at the step that calls jq.");
    expect(screen.getByText("Not on PATH")).toBeInTheDocument();
    expect(screen.getByText("brew install jq")).toBeInTheDocument();

    const installs = screen.getAllByRole("button", { name: "Install…" });
    expect(installs).toHaveLength(2); // the banner and the Command section
    fireEvent.click(installs[0]);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("cli-install-command")).toHaveTextContent("brew install jq");
    expect(api.install).not.toHaveBeenCalled();
  });

  test("each skill that needs it opens that skill's Requires tab", async () => {
    api.get.mockResolvedValue(UV_READY);
    renderAt("uv");
    const link = await screen.findByRole("link", { name: "gh-triage" });
    expect(link).toHaveAttribute("href", "/skills/gh-triage/requires");
    expect(screen.getByText("needs ≥ 0.4")).toBeInTheDocument();
    expect(screen.queryByTestId("cli-problem")).toBeNull();
  });

  test("a command no skill requires says so", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    api.get.mockRejectedValue(new ApiError("CLI_NOT_REQUIRED", "nope"));
    renderAt("nothing");
    expect(await screen.findByText("Couldn't open this command")).toBeInTheDocument();
    expect(screen.getByText("No skill requires this command")).toBeInTheDocument();
  });
});
