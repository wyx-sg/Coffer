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
import { acceptance } from "@/test/acceptance";
import {
  DEMO_INTERFACE,
  GCLOUD_LOGGED_OUT,
  GH_OUTDATED,
  JQ_MISSING,
  NOT_READ,
  UV_MISSING_FOR_SERVER,
  UV_READY,
} from "@/test/cliFixtures";
import { ClisPage } from "./ClisPage";

vi.mock("@/lib/api/clis", () => ({
  clisApi: {
    list: vi.fn(),
    checkAll: vi.fn(),
    get: vi.fn(),
    add: vi.fn(),
    preview: vi.fn(),
    edit: vi.fn(),
    remove: vi.fn(),
    interface: vi.fn(),
    readInterface: vi.fn(),
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
            <Route path="/clis/:command/:tab" element={<ClisPage />} />
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
  api.interface.mockResolvedValue(NOT_READ);
  api.readInterface.mockResolvedValue(DEMO_INTERFACE);
  listAgents.mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
  });
});
afterEach(() => vi.clearAllMocks());

describe("ClisPage", () => {
  acceptance("web-ui", "the CLIs page lists problems first", async () => {
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

  acceptance("web-ui", "a CLI that needs the user offers a prompt for an agent", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { unmount } = renderPage("/clis/jq");
    const banner = await screen.findByTestId("cli-problem");
    expect(banner).toHaveTextContent("jq isn't installed — 2 skills affected");
    expect(banner).toHaveTextContent("gh-triage, log-digest will fail at the step that calls jq.");
    expect(screen.getByText("Not on PATH")).toBeInTheDocument();
    // The action is in the pane's header, not the banner; nothing installs.
    expect(within(banner).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: /Install|Update/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(JQ_MISSING.handoff?.prompt);

    // Ask an agent: the draft opens at once with the prompt, unsent.
    fireEvent.click(await screen.findByRole("button", { name: "Ask an agent" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByTestId("draft")).toHaveTextContent(JQ_MISSING.handoff?.prompt ?? "");
    unmount();

    // With no managed agent available only Copy prompt is offered.
    listAgents.mockResolvedValue({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: false }],
    });
    renderPage("/clis/jq");
    expect(await screen.findByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    await waitFor(() => expect(listAgents).toHaveBeenCalledTimes(2));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("button", { name: "Ask an agent" })).toBeNull();
  });

  acceptance("web-ui", "check again after logging in", async () => {
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
    expect(banner).toHaveTextContent("gh-triage will fail at the step that calls gcloud.");
    // Coffer never runs the login and shows no command for it: the header
    // hands it to an agent.
    expect(screen.queryByText("gcloud auth login")).toBeNull();
    expect(screen.queryByText(/in a terminal/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();

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

  acceptance("web-ui", "a CLI an MCP server starts with lists that server", async () => {
    api.list.mockResolvedValue(listOf([UV_MISSING_FOR_SERVER, GH_OUTDATED]));
    renderPage("/clis/uv");
    const banner = await screen.findByTestId("cli-problem");
    expect(rowOf("uv")).toHaveTextContent("Not found · duckdb needs it");
    expect(rowOf("uv")).toHaveTextContent("1 server · 1 skill");
    expect(screen.getByText("uv · needed by 1 MCP server and 1 skill")).toBeInTheDocument();
    expect(banner).toHaveTextContent("uv isn't installed — 1 MCP server and 1 skill affected");
    expect(banner).toHaveTextContent(
      "duckdb can't start, and data-profiling fails at the step that calls uv.",
    );
    expect(screen.getByRole("link", { name: "duckdb" })).toHaveAttribute(
      "href",
      "/mcp-servers/duckdb",
    );
    expect(screen.getByText("starts with uvx")).toBeInTheDocument();
    expect(screen.getByText("MCP server")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "data-profiling" })).toHaveAttribute(
      "href",
      "/skills/data-profiling/requires",
    );
    expect(screen.getByText("No login needed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
  });

  test("a command nothing knows says so", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    api.get.mockRejectedValue(new ApiError("CLI_NOT_KNOWN", "nope"));
    renderPage("/clis/nothing");
    expect(await screen.findByText("Couldn't open this command")).toBeInTheDocument();
    expect(
      screen.getByText("No skill, MCP server or added tool is called that"),
    ).toBeInTheDocument();
  });

  test("no tool and no requires: shows the empty state with Add and the docs link", async () => {
    api.list.mockResolvedValue({
      items: [],
      warnings: [{ skill_uid: "sk-x", skill_name: "x", message: "entry 1 is not understood" }],
    });
    renderPage();
    expect(await screen.findByText("No command-line tools yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add a command-line tool" })).toHaveLength(2);
    expect(screen.getByRole("link", { name: /How requires: works/ })).toHaveAttribute(
      "href",
      expect.stringContaining("/guides/clis"),
    );
    expect(screen.getByText("x: entry 1 is not understood")).toBeInTheDocument();
  });
});
