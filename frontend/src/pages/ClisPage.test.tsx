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
  GCLOUD_LOGGED_OUT,
  DEMO_ADDED,
  GH_OUTDATED,
  JQ_MISSING,
  UV_MISSING_FOR_SERVER,
  UV_READY,
} from "@/test/cliFixtures";
import { ClisPage } from "./ClisPage";

vi.mock("@/lib/api/clis", () => ({
  clisApi: {
    list: vi.fn(),
    checkAll: vi.fn(),
    check: vi.fn(),
    get: vi.fn(),
    add: vi.fn(),
    preview: vi.fn(),
    edit: vi.fn(),
    remove: vi.fn(),
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
  acceptance("web-ui", "the CLIs page lists problems first", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Needs attention" });
    expect(group("Needs attention")).toEqual(["jq", "gh", "gcloud"]);
    expect(group("Ready")).toEqual(["uv"]);

    expect(rowOf("jq")).toHaveTextContent("Not found · 2 skills need it");
    expect(rowOf("gh")).toHaveTextContent("2.30.0 · needs ≥ 2.40");
    expect(rowOf("gcloud")).toHaveTextContent("Not logged in · 1 skill needs it");
    expect(rowOf("uv")).toHaveTextContent("0.4.18 · 1 skill");

    // No command in the address: the first row is open beside the list.
    expect(paneTitle()).toBe("jq");
    expect(rowOf("jq")).toHaveAttribute("aria-current", "page");

    fireEvent.click(rowOf("gh"));
    expect(screen.getByTestId("where")).toHaveTextContent("/clis/gh");
    expect(paneTitle()).toBe("gh");
    expect(screen.getByTestId("cli-problem")).toHaveTextContent(
      "gh 2.30.0 is older than gh-triage and release-notes need",
    );
    expect(screen.getByTestId("cli-problem")).toHaveTextContent(
      "gh-triage and release-notes need gh ≥ 2.40 and fail at the step that calls it.",
    );
    // One page, no tab strip.
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.getByRole("heading", { name: "On this machine" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needed by" })).toBeInTheDocument();
  });

  test("group titles are plain text like the MCP and Skills lists, not upper-case", async () => {
    renderPage();
    const title = (await screen.findByRole("region", { name: "Needs attention" })).querySelector(
      "h2",
    );
    expect(title?.className).not.toMatch(/uppercase/);
  });

  test("the filter narrows the list", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Needs attention" });
    fireEvent.change(screen.getByRole("textbox", { name: "Filter CLIs" }), {
      target: { value: "cloud" },
    });
    expect(group("Needs attention")).toEqual(["gcloud"]);
    expect(screen.queryByRole("region", { name: "Ready" })).toBeNull();
  });

  acceptance("web-ui", "a CLI that needs the user offers a prompt for an agent", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { unmount } = renderPage("/clis/jq");
    const banner = await screen.findByTestId("cli-problem");
    expect(banner).toHaveTextContent("jq isn’t found on this machine");
    expect(banner).toHaveTextContent(
      "gh-triage and log-digest fail at the step that calls jq. Hand the install to an agent, then check again.",
    );
    expect(screen.getByText("Not on PATH")).toBeInTheDocument();
    // The fix is in the banner: Check again, then the hand-off; nothing installs.
    expect(within(banner).getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Install|Update/ })).toBeNull();

    // Copy prompt lives in the ▾ menu of the split button.
    fireEvent.click(await screen.findByRole("button", { name: "More options" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Copy prompt/ }));
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
    api.check.mockResolvedValue(loggedIn);
    renderPage("/clis/gcloud");

    const banner = await screen.findByTestId("cli-problem");
    expect(banner).toHaveTextContent("gcloud isn’t logged in");
    expect(banner).toHaveTextContent("gh-triage fails at the step that calls gcloud.");
    expect(banner).toHaveTextContent("gcloud auth print-access-token didn’t succeed at");
    // Coffer never runs the login and shows no command for it: the banner
    // hands it to an agent.
    expect(screen.queryByText("gcloud auth login")).toBeNull();
    expect(await within(banner).findByRole("button", { name: "Ask an agent" })).toBeInTheDocument();

    // The banner's Check again re-checks this one command, not all of them.
    fireEvent.click(within(banner).getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.check).toHaveBeenCalledWith("gcloud"));
    expect(api.checkAll).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("cli-problem")).toBeNull());
    expect(screen.getByText("Logged in")).toBeInTheDocument();
    expect(rowOf("gcloud")).toHaveTextContent("480.0.0 · logged in");
    // Ready: no hand-off.
    expect(screen.queryByRole("button", { name: "Ask an agent" })).toBeNull();
  });

  test("the header's Check again re-checks every command and is the primary button", async () => {
    api.checkAll.mockResolvedValue(listOf([UV_READY]));
    renderPage("/clis/uv");
    await screen.findByRole("region", { name: "Ready" });
    const header = screen.getAllByRole("banner")[0];
    fireEvent.click(within(header).getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.checkAll).toHaveBeenCalledTimes(1));
    expect(within(header).getByRole("button", { name: "Add CLI" })).toBeInTheDocument();
  });

  test("each skill that needs it opens that skill's Requires tab", async () => {
    renderPage("/clis/uv");
    const link = await screen.findByRole("link", { name: /gh-triage/ });
    expect(link).toHaveAttribute("href", "/skills/gh-triage/requires");
    expect(link).toHaveTextContent("Skill");
    expect(link).toHaveTextContent("≥ 0.4");
    expect(screen.getByText("needs ≥ 0.4")).toBeInTheDocument();
    expect(screen.queryByTestId("cli-problem")).toBeNull();
  });

  acceptance("web-ui", "a CLI an MCP server starts with lists that server", async () => {
    api.list.mockResolvedValue(listOf([UV_MISSING_FOR_SERVER, GH_OUTDATED]));
    renderPage("/clis/uv");
    const banner = await screen.findByTestId("cli-problem");
    expect(rowOf("uv")).toHaveTextContent("Not found · duckdb can’t start");
    expect(screen.getByText("needed by 1 MCP server and 1 skill")).toBeInTheDocument();
    expect(banner).toHaveTextContent("uv isn’t found on this machine");
    expect(banner).toHaveTextContent(
      "duckdb can’t start, and data-profiling fails at the step that calls uv.",
    );
    expect(screen.getByRole("link", { name: /duckdb/ })).toHaveAttribute(
      "href",
      "/mcp-servers/duckdb",
    );
    expect(screen.getByText("starts with uvx")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /data-profiling/ })).toHaveAttribute(
      "href",
      "/skills/data-profiling/requires",
    );
    expect(screen.getByText("No login needed")).toBeInTheDocument();
    expect(await within(banner).findByRole("button", { name: "Ask an agent" })).toBeInTheDocument();
  });

  acceptance(
    "web-ui",
    "a CLI added by hand has Edit and Remove, a required one has neither",
    async () => {
      api.list.mockResolvedValue(listOf([DEMO_ADDED, UV_READY]));
      renderPage("/clis/demo");
      await screen.findByRole("heading", { level: 2, name: "demo" });
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
      expect(screen.getByText(/No skill or MCP server requires it/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "More actions for demo" }));
      // Remove is the only item: no separator above it.
      expect(screen.getAllByRole("menuitem")).toHaveLength(1);
      expect(within(screen.getByRole("menu")).queryByRole("separator")).toBeNull();
      fireEvent.click(await screen.findByRole("menuitem", { name: "Remove" }));
      expect(await screen.findByText("Remove demo?")).toBeInTheDocument();
      expect(screen.getByText(/The tool stays installed on this machine/)).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      fireEvent.click(rowOf("uv"));
      await screen.findByRole("heading", { level: 2, name: "uv" });
      expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
      expect(screen.queryByRole("button", { name: "More actions for uv" })).toBeNull();
    },
  );

  test("a command nothing knows says so", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    api.get.mockRejectedValue(new ApiError("CLI_NOT_KNOWN", "nope"));
    renderPage("/clis/nothing");
    expect(await screen.findByText("Couldn't open this command")).toBeInTheDocument();
    expect(
      screen.getByText("No skill, MCP server or added tool is called that"),
    ).toBeInTheDocument();
  });

  acceptance("web-ui", "the empty CLIs page offers Add CLI and the docs", async () => {
    api.list.mockResolvedValue({ items: [], warnings: [] });
    renderPage();
    expect(await screen.findByText("No command-line tools yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add CLI" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Check again" })).toBeNull();
    expect(screen.getByRole("link", { name: /How requires: works/ })).toHaveAttribute(
      "href",
      expect.stringContaining("/guides/clis"),
    );
  });

  test("skipped requires: entries are one grey line under the subtitle, with View to Skills", async () => {
    api.list.mockResolvedValue({
      items: [JQ_MISSING],
      warnings: [
        { skill_uid: "sk-x", skill_name: "x", message: "entry 1 is not understood" },
        { skill_uid: "sk-y", skill_name: "y", message: "entry 2 is not understood" },
      ],
    });
    renderPage();
    const line = await screen.findByTestId("cli-warnings");
    expect(line).toHaveTextContent("2 requires: entries in skills couldn’t be read");
    expect(within(line).getByRole("link", { name: "View" })).toHaveAttribute("href", "/skills");
    expect(screen.queryByRole("alert")).not.toHaveTextContent(/skipped/);
  });
});
