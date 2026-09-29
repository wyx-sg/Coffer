// src/components/palette/CommandPalette.test.tsx — the palette's scenarios (change revise-web-ui-ia, web-ui "Jump to any page or object from a command palette").
//
// Only the network boundary is mocked: `getApiClient()` (resources, daemon
// status) and `call()` (agents, skills, providers, knowledge, memory). The
// list hooks, the query cache, the router and the Settings opener are real.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { ApiError } from "@/lib/api/errors";
import { CommandPalette } from "./CommandPalette";

let api: ApiClientMock;
vi.mock("@/lib/api/client", () => ({ getApiClient: () => api }));

const call = vi.fn();
vi.mock("@/lib/api/call", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/call")>();
  return { ...actual, call: (...args: unknown[]) => call(...args) };
});

type Row = { uid: string; name: string; title: string | null };

const MCP: Row[] = [{ uid: "u-gh", name: "github-mcp", title: "Octo bridge" }];
const SKILLS: Row[] = [{ uid: "s-pdf", name: "pdf", title: null }];
const COLLECTIONS: Row[] = [{ uid: "k-notes", name: "team-notes", title: null }];

let features: Record<string, boolean>;
let daemonUp: boolean;
/** Per path: what `call()` answers. A function lets a test hang or reject. */
let callAnswers: Record<string, () => Promise<unknown>>;

function never(): Promise<unknown> {
  return new Promise(() => {});
}

beforeEach(() => {
  features = { knowledge: true, memory: true, vault_sync: true };
  daemonUp = true;
  callAnswers = {
    "/agents": async () => ({ items: [] }),
    "/skills": async () => ({ items: SKILLS }),
    "/providers": async () => ({ providers: [] }),
    "/knowledge/collections": async () => ({ collections: COLLECTIONS }),
    "/memory/partitions": async () => ({ partitions: [] }),
  };
  call.mockImplementation((path: string) => {
    const answer = callAnswers[path];
    return answer ? answer() : Promise.reject(new Error(`unexpected ${path}`));
  });
  api = mockApiClient({
    GET: vi.fn(async (path: string, init?: unknown) => {
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
  return <div data-testid="location">{location.pathname}</div>;
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
const options = () => screen.queryAllByRole("option").map((o) => o.textContent ?? "");
const group = (name: string) => screen.getByRole("group", { name });

/** Wait until the daemon status has answered (the feature gates depend on it). */
async function settled() {
  await waitFor(() => expect(api.GET).toHaveBeenCalledWith("/daemon/status"));
  await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
}

describe("CommandPalette", () => {
  // revise-web-ui-ia: web-ui "the palette jumps to a page"
  test("typing 'act' and Enter opens /activity and closes the palette", async () => {
    renderPalette();
    type("act");
    expect(options()[0]).toBe("Activity");
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/activity");
    expect(screen.getByTestId("open")).toHaveTextContent("false");
    await waitFor(() => expect(screen.queryByRole("combobox")).not.toBeInTheDocument());
  });

  // revise-web-ui-ia: web-ui "the palette jumps to an object"
  test("an MCP server is found by its name and by its title, and opens its detail page", async () => {
    renderPalette();
    await settled();
    type("github");
    expect(within(group("Objects")).getByRole("option")).toHaveTextContent("Octo bridge");
    type("octo");
    const row = within(group("Objects")).getByRole("option");
    expect(row).toHaveTextContent("github-mcp");
    expect(row).toHaveTextContent("MCP server");
    fireEvent.click(row);
    expect(screen.getByTestId("location")).toHaveTextContent("/mcp-servers/github-mcp");
    expect(screen.getByTestId("open")).toHaveTextContent("false");
  });

  // revise-web-ui-ia: web-ui "the palette offers no actions"
  test("every entry navigates and choosing one sends no request that changes state", async () => {
    renderPalette();
    await settled();
    const count = screen.getAllByRole("option").length;
    // 15 sidebar entries + 5 Settings tabs + one MCP server, one skill, one collection.
    expect(count).toBe(23);
    const seen: string[] = [];
    for (let i = 0; i < count; i += 1) {
      fireEvent.click(screen.getByText("reopen"));
      await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(count));
      fireEvent.click(screen.getAllByRole("option")[i]);
      seen.push(screen.getByTestId("location").textContent ?? "");
    }
    expect(new Set(seen).size).toBe(count);
    expect(api.POST).not.toHaveBeenCalled();
    expect(api.PATCH).not.toHaveBeenCalled();
    expect(api.DELETE).not.toHaveBeenCalled();
    for (const [, options] of call.mock.calls) {
      expect((options as { method?: string } | undefined)?.method ?? "GET").toBe("GET");
    }
  });

  // revise-web-ui-ia: web-ui "the palette leaves out switched-off features"
  test("with knowledge switched off neither its page nor a collection is listed", async () => {
    features = { knowledge: false, memory: true, vault_sync: true };
    renderPalette();
    await settled();
    type("knowledge");
    expect(options()).toEqual([]);
    type("team-notes");
    expect(options()).toEqual([]);
    expect(call).not.toHaveBeenCalledWith("/knowledge/collections");
  });

  // revise-web-ui-ia: web-ui "the palette lists pages while objects load"
  test("pages are listed and open while the object lists are still loading", async () => {
    for (const path of Object.keys(callAnswers)) callAnswers[path] = never;
    renderPalette();
    type("act");
    expect(within(group("Pages")).getByRole("option")).toHaveTextContent("Activity");
    expect(within(group("Objects")).getByText("Loading…")).toBeInTheDocument();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/activity");
  });

  // revise-web-ui-ia: web-ui "a failing kind leaves the rest of the palette working"
  test("a failing skills list shows its error while MCP servers and pages still work", async () => {
    callAnswers["/skills"] = () => Promise.reject(new ApiError("INTERNAL_ERROR", "boom"));
    renderPalette();
    await settled();
    const objects = group("Objects");
    expect(within(objects).getByText("Skill: couldn't load the list")).toBeInTheDocument();
    const server = within(objects).getByRole("option", { name: /Octo bridge/ });
    expect(within(objects).queryByRole("option", { name: /pdf/ })).not.toBeInTheDocument();
    expect(within(group("Pages")).getAllByRole("option")).toHaveLength(20);
    fireEvent.click(server);
    expect(screen.getByTestId("location")).toHaveTextContent("/mcp-servers/github-mcp");
  });

  // revise-web-ui-ia: web-ui "the palette with the daemon offline"
  test("with the daemon unreachable it lists pages only and says objects need the daemon", async () => {
    daemonUp = false;
    renderPalette();
    expect(await screen.findByText(/Objects need the daemon/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Objects" })).not.toBeInTheDocument();
    expect(within(group("Pages")).getAllByRole("option").length).toBeGreaterThan(0);
    expect(call).not.toHaveBeenCalled();
  });

  // revise-web-ui-ia: web-ui "the palette says when nothing matches"
  test("a query nothing matches says there are no results", async () => {
    renderPalette();
    await settled();
    type("zzqx");
    expect(options()).toEqual([]);
    expect(screen.getByText("No results for “zzqx”")).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "Jump to any page or object from a command palette" — Settings tabs
  test("'data' and Enter opens Settings on the Data tab", () => {
    renderPalette();
    type("data");
    expect(options()[0]).toBe("Settings › Data");
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/settings/data");
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
});
