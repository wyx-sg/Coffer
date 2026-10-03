// src/components/palette/CommandPalette.test.tsx — the palette's scenarios (spec web-ui "Jump to any page or object from a command palette").
//
// Only the network boundary is mocked: `getApiClient()` (resources, daemon
// status, and the list routes of agents, skills, providers, knowledge, memory). The
// list hooks, the query cache, the router and the Settings opener are real.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { ApiError } from "@/lib/api/errors";
import { CommandPalette } from "./CommandPalette";

let api: ApiClientMock;
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => api,
}));

/** Every list route the palette reads through the client, by path (see `callAnswers`). */
const call = vi.fn();

type Row = { uid: string; name: string; title: string | null };

const MCP: Row[] = [{ uid: "u-gh", name: "github-mcp", title: "Octo bridge" }];
const SKILLS = [{ uid: "s-pdf", name: "pdf", title: null, bindings: [] }];
const COLLECTIONS: Row[] = [{ uid: "k-notes", name: "team-notes", title: null }];

const ALL_ON = { knowledge: true, memory: true, sync: true, models: true };
const ALL_OFF = { knowledge: false, memory: false, sync: false, models: false };
let features: Record<string, boolean>;
let daemonUp: boolean;
/** Per path: what the list route answers. A function lets a test hang or reject. */
let callAnswers: Record<string, () => Promise<unknown>>;

function never(): Promise<unknown> {
  return new Promise(() => {});
}

beforeEach(() => {
  // The Recent group is remembered per browser; every test starts without one.
  localStorage.clear();
  features = ALL_ON;
  daemonUp = true;
  callAnswers = {
    "/agents": async () => ({ items: [] }),
    "/skills": async () => ({ items: SKILLS }),
    "/providers": async () => ({ providers: [] }),
    "/knowledge/collections": async () => ({ collections: COLLECTIONS }),
    "/memory/partitions": async () => ({ partitions: [] }),
  };
  call.mockImplementation(async (path: string) => {
    const answer = callAnswers[path];
    if (!answer) throw new Error(`unexpected ${path}`);
    return { data: await answer(), error: undefined };
  });
  api = mockApiClient({
    GET: vi.fn(async (path: string, init?: unknown) => {
      if (path in callAnswers) return call(path, init);
      if (path === "/daemon/status") {
        return daemonUp
          ? { data: { features }, error: undefined }
          : { data: undefined, error: { error: { code: "DAEMON_OFFLINE", message: "down" } } };
      }
      if (path === "/resources") {
        const kind = (init as { params: { query: { kind?: string } } }).params.query.kind;
        if (kind === "mcp_server") return { data: { resources: MCP }, error: undefined };
        if (kind === "channel") return { data: { resources: [] }, error: undefined };
      }
      return { data: undefined, error: { error: { code: "NOT_FOUND", message: path } } };
    }),
  });
});

afterEach(() => {
  call.mockReset();
});

function Where() {
  const location = useLocation();
  const under = (location.state as { backgroundLocation?: { pathname: string } } | null)
    ?.backgroundLocation?.pathname;
  return (
    <div data-testid="location" data-under={under ?? ""}>
      {location.pathname}
    </div>
  );
}

function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        reopen
      </button>
      <div data-testid="open">{String(open)}</div>
      <CommandPalette open={open} onOpenChange={setOpen} />
      <Where />
    </>
  );
}

function renderPalette() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/agents"]}>
        <Harness />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const input = () => screen.getByRole("combobox");
const type = (text: string) => fireEvent.change(input(), { target: { value: text } });
/** Each row's label (its meta — kind, status, shortcut — left out). */
const options = () => screen.queryAllByTestId("palette-row-label").map((o) => o.textContent ?? "");
const group = (name: string) => screen.getByRole("group", { name });

/** Wait until the daemon status has answered (the feature gates depend on it). */
async function settled() {
  await waitFor(() => expect(api.GET).toHaveBeenCalledWith("/daemon/status"));
  await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
}

describe("CommandPalette", () => {
  acceptance("web-ui", "the palette jumps to a page", async () => {
    renderPalette();
    type("act");
    expect(options()[0]).toBe("Activity");
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/activity");
    expect(screen.getByTestId("open")).toHaveTextContent("false");
    await waitFor(() => expect(screen.queryByRole("combobox")).not.toBeInTheDocument());
  });

  acceptance("web-ui", "the palette jumps to an object", async () => {
    renderPalette();
    await settled();
    type("github");
    expect(within(group("Best match")).getByRole("option")).toHaveTextContent("Octo bridge");
    type("octo");
    const row = within(group("Best match")).getByRole("option");
    expect(row).toHaveTextContent("github-mcp");
    expect(row).toHaveTextContent("MCP server");
    fireEvent.click(row);
    expect(screen.getByTestId("location")).toHaveTextContent("/mcp-servers/github-mcp");
    expect(screen.getByTestId("open")).toHaveTextContent("false");
  });

  acceptance("web-ui", "the palette offers no actions", async () => {
    renderPalette();
    await settled();
    const pages = () => within(group("Pages")).getAllByRole("option");
    // An empty query lists every page: 15 sidebar entries + 6 Settings tabs.
    const count = pages().length;
    expect(count).toBe(21);
    const seen: string[] = [];
    for (let i = 0; i < count; i += 1) {
      fireEvent.click(screen.getByText("reopen"));
      await waitFor(() => expect(pages()).toHaveLength(count));
      fireEvent.click(pages()[i]);
      seen.push(screen.getByTestId("location").textContent ?? "");
    }
    // Objects are listed under a query: each one opens its detail page.
    for (const [query, label] of [
      ["github-mcp", "Octo bridge"],
      ["pdf", "pdf"],
      ["team-notes", "team-notes"],
    ]) {
      fireEvent.click(screen.getByText("reopen"));
      type(query);
      await waitFor(() => expect(options()[0]).toBe(label));
      fireEvent.keyDown(input(), { key: "Enter" });
      seen.push(screen.getByTestId("location").textContent ?? "");
    }
    expect(new Set(seen).size).toBe(count + 3);
    expect(api.POST).not.toHaveBeenCalled();
    expect(api.PATCH).not.toHaveBeenCalled();
    expect(api.DELETE).not.toHaveBeenCalled();
  });

  acceptance("web-ui", "the palette leaves out switched-off features", async () => {
    features = ALL_OFF;
    renderPalette();
    await settled();
    // Their pages are not listed, and nothing of theirs is asked for: no
    // provider, knowledge, memory, sync or usage list is read.
    for (const name of ["Model providers", "Usage", "Knowledge", "Memory", "Sync"]) {
      type(name);
      expect(options()).toEqual([]);
    }
    const asked = call.mock.calls.map(([path]) => path as string);
    expect(asked.filter((p) => /^\/(providers|knowledge|memory|sync|usage)/.test(p))).toEqual([]);
    const kinds = api.GET.mock.calls
      .filter(([path]) => path === "/resources")
      .map(([, init]) => (init as { params: { query: { kind?: string } } }).params.query.kind);
    expect(kinds).not.toContain("provider");
    // The always-on pages stay: Activity, Conversations, Channels and the MCP server list.
    type("activity");
    expect(options()).toEqual(["Activity"]);
    type("channels");
    expect(options()).toEqual(["Channels"]);
    type("conversations");
    expect(options()).toEqual(["Conversations"]);
  });

  // The other half: switched on, the pages are listed.
  test("switched on, a feature's pages and objects are listed", async () => {
    features = ALL_ON;
    renderPalette();
    await settled();
    type("knowledge");
    expect(options()).toContain("Knowledge");
    type("providers");
    expect(options()).toContain("Model providers");
    expect(call.mock.calls.map(([path]) => path)).toContain("/providers");
  });

  acceptance("web-ui", "the palette lists pages while objects load", async () => {
    for (const path of Object.keys(callAnswers)) callAnswers[path] = never;
    renderPalette();
    type("act");
    expect(within(group("Best match")).getByRole("option")).toHaveTextContent("Activity");
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/activity");
  });

  acceptance("web-ui", "a failing kind leaves the rest of the palette working", async () => {
    callAnswers["/skills"] = () => Promise.reject(new ApiError("INTERNAL_ERROR", "boom"));
    renderPalette();
    await settled();
    expect(within(group("Pages")).getAllByRole("option")).toHaveLength(21);
    type("o");
    expect(within(group("Skills")).getByText("Skill: couldn't load the list")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /pdf/ })).not.toBeInTheDocument();
    type("octo");
    const server = screen.getByRole("option", { name: /Octo bridge/ });
    fireEvent.click(server);
    expect(screen.getByTestId("location")).toHaveTextContent("/mcp-servers/github-mcp");
  });

  acceptance("web-ui", "the palette with the daemon offline", async () => {
    daemonUp = false;
    renderPalette();
    expect(await screen.findByText(/Objects need the daemon/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Objects" })).not.toBeInTheDocument();
    expect(within(group("Pages")).getAllByRole("option").length).toBeGreaterThan(0);
    expect(call).not.toHaveBeenCalled();
  });

  acceptance("web-ui", "the palette says when nothing matches", async () => {
    renderPalette();
    await settled();
    type("zzqx");
    expect(options()).toEqual([]);
    expect(screen.getByText("No results for “zzqx”")).toBeInTheDocument();
  });

  // Spec web-ui "Jump to any page or object from a command palette": Settings tabs.
  acceptance("web-ui", "the palette opens a Settings tab over the current page", () => {
    renderPalette();
    type("data");
    expect(options()[0]).toBe("Settings › Data");
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/settings/data");
    // The page the palette was opened from stays underneath the modal.
    expect(screen.getByTestId("location")).toHaveAttribute("data-under", "/agents");
  });

  test("arrow keys move the selection and wrap; the input points at the selected row", () => {
    renderPalette();
    type("s");
    const rows = screen.getAllByRole("option");
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    expect(input()).toHaveAttribute("aria-activedescendant", screen.getAllByRole("option")[1].id);
    fireEvent.keyDown(input(), { key: "ArrowUp" });
    fireEvent.keyDown(input(), { key: "ArrowUp" });
    const last = screen.getAllByRole("option").at(-1)!;
    expect(last).toHaveAttribute("aria-selected", "true");
  });

  acceptance("web-ui", "an empty query shows recent choices above every page", async () => {
    renderPalette();
    await settled();
    expect(screen.queryByRole("group", { name: "Recent" })).not.toBeInTheDocument();
    type("octo");
    fireEvent.keyDown(input(), { key: "Enter" });
    fireEvent.click(screen.getByText("reopen"));
    type("usage");
    fireEvent.keyDown(input(), { key: "Enter" });
    fireEvent.click(screen.getByText("reopen"));
    await waitFor(() => expect(group("Recent")).toBeInTheDocument());
    const recent = within(group("Recent")).getAllByRole("option");
    expect(recent.map((r) => within(r).getByTestId("palette-row-label").textContent)).toEqual([
      "Usage",
      "Octo bridge",
    ]);
    expect(within(group("Pages")).getAllByRole("option")).toHaveLength(21);
  });

  acceptance("web-ui", "a skill result names the agents that get it", async () => {
    callAnswers["/agents"] = async () => ({
      items: [
        { uid: "a-cc", name: "claude-code", display_name: "Claude Code" },
        { uid: "a-cx", name: "codex", display_name: "Codex" },
      ],
    });
    callAnswers["/skills"] = async () => ({
      items: [
        {
          uid: "s-tri",
          name: "issue-triage",
          title: null,
          enabled: true,
          bindings: [
            { agent_uid: "a-cc", agent_name: "claude-code" },
            { agent_uid: "a-cx", agent_name: "codex" },
          ],
        },
      ],
    });
    renderPalette();
    await settled();
    type("issue-tri");
    await waitFor(() =>
      expect(within(group("Best match")).getByRole("option")).toHaveTextContent(
        "issue-triageSkillClaude Code · Codex",
      ),
    );
  });

  acceptance("web-ui", "a query lists only its matches", async () => {
    renderPalette();
    await settled();
    type("octo");
    fireEvent.keyDown(input(), { key: "Enter" });
    fireEvent.click(screen.getByText("reopen"));
    await waitFor(() => expect(group("Recent")).toBeInTheDocument());
    type("usage");
    expect(screen.queryByRole("group", { name: "Recent" })).not.toBeInTheDocument();
    expect(options()).toEqual(expect.arrayContaining(["Usage"]));
    expect(options()).not.toContain("Octo bridge");
  });

  test("Escape closes the palette and focus returns where it was", async () => {
    renderPalette();
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(screen.getByTestId("open")).toHaveTextContent("false");
    const opener = screen.getByText("reopen");
    opener.focus();
    fireEvent.click(opener);
    await waitFor(() => expect(input()).toHaveFocus());
    fireEvent.keyDown(input(), { key: "Escape" });
    await waitFor(() => expect(opener).toHaveFocus());
  });

  test("conversations are asked for by the text typed, 8 at a time, never as a whole list", async () => {
    callAnswers["/chat/conversations"] = async () => ({
      conversations: [{ id: "c1", title: "Deploy plan", running: false, preview: null }],
      next_cursor: null,
    });
    renderPalette();
    await settled();
    // Opened empty, the palette reads the first page of 30.
    const queries = () =>
      call.mock.calls
        .filter(([path]) => path === "/chat/conversations")
        .map(([, init]) => (init as { params: { query: Record<string, unknown> } }).params.query);
    await waitFor(() => expect(queries()).toHaveLength(1));
    expect(queries()[0]).toMatchObject({ limit: 30 });
    expect(queries()[0].q).toBeUndefined();

    type("deploy");
    await waitFor(() => expect(queries()).toHaveLength(2));
    expect(queries()[1]).toMatchObject({ q: "deploy", limit: 8 });
    await waitFor(() => expect(options()).toContain("Deploy plan"));
  });
});
