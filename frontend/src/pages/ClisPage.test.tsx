// src/pages/ClisPage.test.tsx — the CLIs page: the grouped list beside one command, the hand-off to an agent, Check again.
//
// Real QueryClientProvider; only the api modules are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { Cli } from "@/lib/api/clis";
import { readHandoffState } from "@/lib/conversations/handoff";
import { GCLOUD_LOGGED_OUT, GH_OUTDATED, JQ_MISSING, UV_READY } from "@/test/cliFixtures";
import { ClisPage } from "./ClisPage";

vi.mock("@/lib/api/clis", () => ({
  clisApi: {
    list: vi.fn(),
    checkAll: vi.fn(),
    get: vi.fn(),
  },
}));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
const { clisApi } = await import("@/lib/api/clis");
const api = vi.mocked(clisApi);
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgents = vi.mocked(agentProvidersApi.list);

function listOf(items: Cli[]) {
  return { items, warnings: [] };
}

function Where() {
  const { pathname } = useLocation();
  return <div data-testid="where">{pathname}</div>;
}

function Draft() {
  const handoff = readHandoffState(useLocation().state);
  return <div data-testid="draft">{handoff?.prompt}</div>;
}

function renderPage(path = "/clis") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/clis" element={<ClisPage />} />
            <Route path="/clis/:command" element={<ClisPage />} />
            <Route path="/conversations/new" element={<Draft />} />
            <Route path="*" element={null} />
          </Routes>
          <Where />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** The list pane's rows in one group, by command. */
function group(name: string): string[] {
  return within(screen.getByRole("region", { name }))
    .getAllByRole("button")
    .map((b) => b.querySelector(".font-mono")?.textContent ?? "");
}

function rowOf(command: string): HTMLElement {
  const row = screen
    .getAllByRole("button")
    .find((b) => b.querySelector(".font-mono")?.textContent === command);
  if (!row) throw new Error(`no row for ${command}`);
  return row;
}

/** The detail pane's heading. */
function paneTitle(): string {
  return screen.getByRole("heading", { level: 2 }).textContent ?? "";
}

beforeEach(() => {
  // The daemon's order: missing, outdated, logged out, ready.
  api.list.mockResolvedValue(listOf([JQ_MISSING, GH_OUTDATED, GCLOUD_LOGGED_OUT, UV_READY]));
  listAgents.mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
  });
});
afterEach(() => vi.clearAllMocks());

describe("ClisPage", () => {
  // scenario (web-ui, revise-web-ui-ia 7.14d): "the CLIs page lists problems first"
  test("the CLIs page lists problems first", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Needs you" });
    expect(group("Needs you")).toEqual(["jq", "gh", "gcloud"]);
    expect(group("Ready")).toEqual(["uv"]);

    expect(rowOf("jq")).toHaveTextContent("Not found");
    expect(rowOf("gh")).toHaveTextContent("2.30.0 · needs ≥ 2.40");
    expect(rowOf("gh")).toHaveTextContent("2 skills");
    expect(rowOf("gcloud")).toHaveTextContent("Not logged in");
    expect(rowOf("uv")).toHaveTextContent("0.4.18");

    // No command in the address: the first row is open beside the list.
    expect(paneTitle()).toBe("jq");
    expect(rowOf("jq")).toHaveAttribute("aria-current", "page");

    fireEvent.click(rowOf("gh"));
    expect(screen.getByTestId("where")).toHaveTextContent("/clis/gh");
    expect(paneTitle()).toBe("gh");
    expect(screen.getByTestId("cli-problem")).toHaveTextContent(
      "gh 2.30.0 is older than gh-triage, release-notes need",
    );
    expect(screen.getByTestId("cli-problem")).toHaveTextContent("They need gh ≥ 2.40.");
  });

  test("the filter narrows the list", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Needs you" });
    fireEvent.change(screen.getByRole("textbox", { name: "Filter commands" }), {
      target: { value: "cloud" },
    });
    expect(group("Needs you")).toEqual(["gcloud"]);
    expect(screen.queryByRole("region", { name: "Ready" })).toBeNull();
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "a CLI that needs the user offers a prompt for an agent"
  test("a CLI that needs the user offers a prompt for an agent", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderPage("/clis/jq");
    const banner = await screen.findByTestId("cli-problem");
    expect(banner).toHaveTextContent("jq isn't installed — 2 skills affected");
    expect(banner).toHaveTextContent("gh-triage, log-digest will fail at the step that calls jq.");
    expect(screen.getByText("Not on PATH")).toBeInTheDocument();
    // The action is in the pane's header, not the banner; nothing installs.
    expect(within(banner).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: /Install|Update/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(JQ_MISSING.handoff?.prompt);

    // Ask an agent: pick one, then the draft opens with the prompt, unsent.
    fireEvent.click(await screen.findByRole("button", { name: "Ask an agent" }));
    const dialog = await screen.findByRole("dialog");
    const start = within(dialog).getByRole("button", { name: "Start" });
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    expect(await screen.findByTestId("draft")).toHaveTextContent(JQ_MISSING.handoff?.prompt ?? "");
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "check again after logging in"
  test("check again after logging in", async () => {
    const loggedIn = {
      ...GCLOUD_LOGGED_OUT,
      status: "ready" as const,
      login: { ...GCLOUD_LOGGED_OUT.login, state: "logged_in" as const },
      handoff: null,
    };
    api.checkAll.mockResolvedValue(listOf([loggedIn]));
    renderPage("/clis/gcloud");

    const banner = await screen.findByTestId("cli-problem");
    expect(banner).toHaveTextContent("gcloud isn't logged in — 1 skill affected");
    expect(banner).toHaveTextContent("gcloud auth login");
    // Coffer never runs the login: the header hands it to an agent.
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    expect(screen.getByText("Run it in a terminal, then press Check again.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.checkAll).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByTestId("cli-problem")).toBeNull());
    expect(screen.getByText("Logged in")).toBeInTheDocument();
    expect(rowOf("gcloud")).toHaveTextContent("480.0.0 · logged in");
    // Ready: no action in the header.
    expect(screen.queryByRole("button", { name: "Copy prompt" })).toBeNull();
  });

  test("each skill that needs it opens that skill's Requires tab", async () => {
    renderPage("/clis/uv");
    const link = await screen.findByRole("link", { name: "gh-triage" });
    expect(link).toHaveAttribute("href", "/skills/gh-triage/requires");
    expect(screen.getByText("✓ needs ≥ 0.4")).toBeInTheDocument();
    expect(screen.queryByTestId("cli-problem")).toBeNull();
  });

  test("a command no skill requires says so", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    api.get.mockRejectedValue(new ApiError("CLI_NOT_REQUIRED", "nope"));
    renderPage("/clis/nothing");
    expect(await screen.findByText("Couldn't open this command")).toBeInTheDocument();
    expect(screen.getByText("No skill requires this command")).toBeInTheDocument();
  });

  test("no skill declares requires: shows the empty state with the docs link", async () => {
    api.list.mockResolvedValue({
      items: [],
      warnings: [{ skill_uid: "sk-x", skill_name: "x", message: "entry 1 is not understood" }],
    });
    renderPage();
    expect(await screen.findByText("No skill requires a command yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /How requires: works/ })).toHaveAttribute(
      "href",
      expect.stringContaining("/guides/clis"),
    );
    expect(screen.getByText("x: entry 1 is not understood")).toBeInTheDocument();
  });
});
