// src/pages/AgentsPage.test.tsx — the Agents list: two fixed rows, each state's action, first run and the change preview.
//
// The real hooks run against an in-memory daemon behind `call` and
// `getApiClient` (fakeAgentsDaemon), so a registration and a connection
// change the rows the way the daemon would.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentsPage } from "./AgentsPage";
import {
  fakeCallFor,
  fakeDaemon,
  typeRow,
  type FakeDaemon,
} from "@/components/agents/list/fakeAgentsDaemon";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import { fakeApi } from "@/test/fakeApi";

const call = fakeApi();

let daemon: FakeDaemon;

function setDaemon(d: FakeDaemon) {
  daemon = d;
  call.mockImplementation(fakeCallFor(d));
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>
          <AgentsPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const rowOf = (name: string) => screen.getByText(name, { selector: "span" }).closest("tr")!;
const writes = () => daemon.calls.filter((c) => c.method !== "GET");

beforeEach(() => setDaemon(fakeDaemon()));
afterEach(() => vi.clearAllMocks());

describe("AgentsPage", () => {
  acceptance("agent-registry", "desktop app agents page", async () => {
    setDaemon(
      fakeDaemon({
        types: [
          typeRow({ type: "codex", uid: "agt_c" }),
          typeRow({ type: "claude_code", uid: "agt_a" }),
        ],
        connections: {
          agt_a: {
            state: "connected",
            parts: [{ key: "mcp", installed: true, detail: "/bin/coffer" }],
          },
        },
        models: { agt_a: "claude-opus-5-5" },
        onConnection: ["agt_a"],
      }),
    );
    renderPage();
    expect(screen.getByRole("heading", { name: /^agents$/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(3));
    // Exactly the two supported types, Claude Code first, with type, name and directory.
    const [, first, second] = screen.getAllByRole("row");
    expect(first).toHaveTextContent("Claude Code");
    expect(first).toHaveTextContent("~/.claude");
    expect(second).toHaveTextContent("Codex");
    expect(second).toHaveTextContent("~/.codex");
    await waitFor(() => expect(first).toHaveTextContent("claude-opus-5-5"));
    await waitFor(() => expect(within(first).getByText("Connected")).toBeInTheDocument());
    expect(within(first).getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /detect/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  acceptance(
    "agent-registry",
    "the agents page shows both supported agents on first run",
    async () => {
      setDaemon(
        fakeDaemon({ types: [typeRow({ type: "claude_code" }), typeRow({ type: "codex" })] }),
      );
      renderPage();
      const addBoth = await screen.findByRole("button", { name: "Add both" });
      expect(screen.getByText("2 detected, not added")).toBeInTheDocument();
      expect(within(rowOf("Claude Code")).getByRole("button", { name: "Add" })).toBeInTheDocument();
      expect(within(rowOf("Codex")).getByRole("button", { name: "Add" })).toBeInTheDocument();
      expect(screen.getByText(/you review the exact lines/i)).toBeInTheDocument();

      fireEvent.click(addBoth);
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText("Connect 2 agents to Coffer")).toBeInTheDocument();
      expect(within(dialog).getByTestId("change-summary")).toHaveTextContent(
        "4 changes in 2 agents",
      );
      for (const path of ["~/.claude.json", "~/.claude/settings.json", "~/.codex/config.toml"]) {
        expect(within(dialog).getAllByText(path).length).toBeGreaterThan(0);
      }
      expect(writes()).toEqual([]);

      fireEvent.click(within(dialog).getByRole("button", { name: "Apply 4 changes" }));
      await waitFor(() => expect(within(dialog).getByText("Changes applied")).toBeInTheDocument());
      expect(writes().map((c) => `${c.method} ${c.path}`)).toEqual([
        "POST /agents",
        "POST /agents/agt_1/coffer-connection",
        "POST /agents",
        "POST /agents/agt_2/coffer-connection",
      ]);
      expect(writes()[0].body).toEqual({ type: "claude_code" });
      fireEvent.click(within(dialog).getByRole("button", { name: "Done" }));
      await waitFor(() => expect(screen.getByText("2 connected")).toBeInTheDocument());
      expect(screen.queryByRole("button", { name: "Add both" })).not.toBeInTheDocument();
    },
  );

  test("a failed agent fails on its own and Retry re-runs only it", async () => {
    setDaemon(
      fakeDaemon({ types: [typeRow({ type: "claude_code" }), typeRow({ type: "codex" })] }),
    );
    let failOnce = true;
    daemon.fail = (c) => {
      if (c.method === "POST" && c.path === "/agents/agt_2/coffer-connection" && failOnce) {
        failOnce = false;
        return new ApiError("CONFIG_WRITE_FAILED", "hooks.json is locked");
      }
      return undefined;
    };
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Add both" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply 4 changes" }));
    const retry = await within(dialog).findByRole("button", { name: "Retry 2 changes" });
    expect(within(dialog).getByText("Some changes failed")).toBeInTheDocument();
    fireEvent.click(retry);
    await waitFor(() => expect(within(dialog).getByText("Changes applied")).toBeInTheDocument());
    // The registration that succeeded is not repeated.
    expect(writes().filter((c) => c.path === "/agents")).toHaveLength(2);
    expect(writes().at(-1)?.path).toBe("/agents/agt_2/coffer-connection");
  });

  // One page with both rows covers both scenarios: Claude Code not installed, Codex left behind.
  const notInstalledAndLeftBehind = async () => {
    setDaemon(
      fakeDaemon({
        types: [
          typeRow({
            type: "claude_code",
            state: "missing",
            addable: false,
            version: null,
            install_handoff: { prompt: "Please install Claude Code on this machine." },
          }),
          typeRow({
            type: "codex",
            state: "config_only",
            addable: false,
            version: null,
            install_handoff: { prompt: "Please reinstall OpenAI Codex on this machine." },
          }),
        ],
      }),
    );
    renderPage();
    const claude = await waitFor(() => rowOf("Claude Code"));
    await waitFor(() =>
      expect(within(claude).getByRole("button", { name: "Copy prompt" })).toBeInTheDocument(),
    );
    expect(within(rowOf("Codex")).getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    expect(within(claude).getAllByText("Not installed").length).toBeGreaterThan(0);
    expect(claude).toHaveTextContent("An agent can install it — copy the prompt");
    expect(document.body).not.toHaveTextContent(/npm|install -g/);
    expect(screen.queryByRole("button", { name: "Add" })).not.toBeInTheDocument();
    expect(screen.getByText("Config left behind — program not found")).toBeInTheDocument();
    // The warning under the Codex row names the folder and the program, and
    // offers the reinstall prompt.
    const notice = screen.getByText(/is still here but there is no/);
    expect(notice).toHaveTextContent("~/.codex is still here but there is no codex on PATH");
    expect(screen.getByRole("button", { name: "Reveal folder" })).toBeInTheDocument();
    // Not added, so nothing to remove from the list.
    expect(screen.queryByRole("button", { name: "Remove from list" })).not.toBeInTheDocument();
  };
  acceptance(
    "agent-registry",
    "an agent that is not installed shows how to install it",
    notInstalledAndLeftBehind,
  );
  acceptance(
    "agent-registry",
    "a leftover config directory reads as config left behind",
    notInstalledAndLeftBehind,
  );

  acceptance("agent-registry", "an installed agent that has never run can be added", async () => {
    setDaemon(
      fakeDaemon({
        types: [
          typeRow({ type: "claude_code", uid: "agt_a" }),
          typeRow({ type: "codex", state: "installed_never_run" }),
        ],
      }),
    );
    renderPage();
    await waitFor(() => expect(rowOf("Codex")).toHaveTextContent("not created"));
    fireEvent.click(within(rowOf("Codex")).getByRole("button", { name: "Add" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Connect Codex to Coffer")).toBeInTheDocument();
    expect(within(dialog).getAllByText("~/.codex/").length).toBeGreaterThan(0);
    expect(within(dialog).getByText(/Coffer creates ~\/\.codex for it/)).toBeInTheDocument();
    expect(writes()).toEqual([]);
  });

  acceptance(
    "agent-registry",
    "repairing a partial connection previews the missing parts",
    async () => {
      setDaemon(
        fakeDaemon({
          types: [typeRow({ type: "claude_code", uid: "agt_a" }), typeRow({ type: "codex" })],
          connections: {
            agt_a: {
              state: "partial",
              parts: [
                { key: "mcp", installed: true, detail: "/bin/coffer" },
                { key: "memory_hook", installed: false, detail: null },
              ],
            },
          },
        }),
      );
      renderPage();
      const repair = await waitFor(() =>
        within(rowOf("Claude Code")).getByRole("button", { name: "Repair" }),
      );
      await waitFor(() =>
        expect(rowOf("Claude Code")).toHaveTextContent("Memory hook not written"),
      );
      fireEvent.click(repair);
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText("Repair Claude Code’s connection")).toBeInTheDocument();
      expect(within(dialog).getByTestId("change-summary")).toHaveTextContent("1 change in 1 agent");
      fireEvent.click(within(dialog).getByRole("button", { name: "Apply 1 change" }));
      await waitFor(() => expect(within(dialog).getByText("Changes applied")).toBeInTheDocument());
      expect(writes().map((c) => `${c.method} ${c.path}`)).toEqual([
        "POST /agents/agt_a/coffer-connection",
      ]);
      fireEvent.click(within(dialog).getByRole("button", { name: "Done" }));
      await waitFor(() =>
        expect(within(rowOf("Claude Code")).getByText("Connected")).toBeInTheDocument(),
      );
    },
  );

  // Codex is installed_active and not added; Claude Code is added.
  const rowMenuAndNoDetect = async () => {
    setDaemon(
      fakeDaemon({
        types: [typeRow({ type: "claude_code", uid: "agt_a" }), typeRow({ type: "codex" })],
      }),
    );
    renderPage();
    await waitFor(() =>
      expect(within(rowOf("Codex")).getByRole("button", { name: "Add" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /add agent/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /detect/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Claude Code" }));
    const menu = await screen.findByRole("menu");
    const items = within(menu)
      .getAllByRole("menuitem")
      .map((i) => i.textContent);
    expect(items).toEqual([
      "Use a different config directory…",
      "Reveal config directory",
      "Copy uid",
      "Turn off",
      "Remove from Coffer",
    ]);
    expect(screen.queryByRole("textbox", { name: /name|title/i })).not.toBeInTheDocument();
  };
  acceptance(
    "agent-registry",
    "a row's menu offers a different config directory",
    rowMenuAndNoDetect,
  );
  acceptance(
    "agent-registry",
    "the agents page detects candidates without a detect action",
    rowMenuAndNoDetect,
  );

  test("keeps the header up over skeleton rows while the types load", () => {
    call.mockImplementation(() => new Promise(() => {}));
    renderPage();
    expect(screen.getByRole("heading", { name: /agents/i })).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });

  test("a failed read shows the error with Retry", async () => {
    daemon.fail = () => new ApiError("INTERNAL_ERROR", "kaboom");
    renderPage();
    expect(await screen.findByText(/failed to load agents/i)).toBeInTheDocument();
    daemon.fail = undefined;
    daemon.types = [typeRow({ type: "claude_code" }), typeRow({ type: "codex" })];
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("button", { name: "Add both" })).toBeInTheDocument();
  });

  it("a built-in login shows the agent's own default, never a stale provider model", async () => {
    setDaemon(
      fakeDaemon({
        types: [typeRow({ type: "codex", uid: "agt_c" })],
        models: { agt_c: "agnes-2.0-flash" },
        catalogue: { codex: ["gpt-5", "gpt-6-astra"] },
        nativeDefaults: { codex: "gpt-6-astra" },
      }),
    );
    renderPage();
    const row = await screen.findByRole("row", { name: /Codex/ });
    await waitFor(() => expect(row).toHaveTextContent("gpt-6-astra"));
    expect(row).not.toHaveTextContent("agnes-2.0-flash");
  });

  it("says the agent chooses when its own config names no default", async () => {
    setDaemon(
      fakeDaemon({
        types: [typeRow({ type: "codex", uid: "agt_c" })],
        models: { agt_c: "agnes-2.0-flash" },
        catalogue: { codex: ["gpt-5", "gpt-6-astra"] },
      }),
    );
    renderPage();
    const row = await screen.findByRole("row", { name: /Codex/ });
    await waitFor(() => expect(row).toHaveTextContent("Chosen by the agent"));
    expect(row).not.toHaveTextContent("gpt-5");
    expect(row).not.toHaveTextContent("agnes-2.0-flash");
  });

  it("shows a pending state while a disconnect runs, and the row settles after", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const daemon = fakeDaemon({
      types: [typeRow({ type: "claude_code", uid: "agt_a" })],
      connections: {
        agt_a: {
          state: "connected",
          parts: [{ key: "mcp", installed: true, detail: "/bin/coffer" }],
        },
      },
      hold: (call) => (call.method === "DELETE" ? gate : undefined),
    });
    setDaemon(daemon);
    renderPage();
    const row = await screen.findByRole("row", { name: /Claude Code/ });
    fireEvent.click(await within(row).findByRole("button", { name: "Disconnect" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /^disconnect/i }));
    await waitFor(() => expect(within(row).getByText("Disconnecting…")).toBeInTheDocument());
    // The dialog's modal layer hides the row from the accessibility tree.
    expect(within(row).getByRole("button", { name: "Disconnect", hidden: true })).toBeDisabled();
    release();
    await waitFor(() => expect(within(row).queryByText("Disconnecting…")).not.toBeInTheDocument());
  });
});
