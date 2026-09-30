// src/components/palette/CommandPalette.test.tsx — the palette's scenarios (spec web-ui "Jump to any page or object from a command palette").
//
// Only the network boundary is mocked: `getApiClient()` (resources, daemon
// status) and `call()` (agents, skills, providers, knowledge, memory). The
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
vi.mock("@/lib/api/client", () => ({ getApiClient: () => api }));

const call = vi.fn();
vi.mock("@/lib/api/call", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/call")>();
  return { ...actual, call: (...args: unknown[]) => call(...args) };
});

// No real page carries an experimental feature, so the gate is tested on a
// test-only entry flagged with one; it is off unless a test says otherwise.
vi.mock("@/lib/navigation", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/navigation")>();
  const { FlaskConical } = await import("lucide-react");
  const fake = { to: "/fake", labelKey: "Fake page", icon: FlaskConical, feature: "fake_feature" };
  return { ...real, NAV_ENTRIES: [...real.NAV_ENTRIES, fake] };
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
  // The Recent group is remembered per browser; every test starts without one.
  localStorage.clear();
  features = { fake_feature: false };
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
    // An empty query lists every page: 15 sidebar entries + 5 Settings tabs.
    const count = pages().length;
    expect(count).toBe(20);
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
    for (const [, options] of call.mock.calls) {
      expect((options as { method?: string } | undefined)?.method ?? "GET").toBe("GET");
    }
  });

  acceptance("web-ui", "the palette leaves out switched-off features", async () => {
    renderPalette();
    await settled();
    type("fake page");
    expect(options()).toEqual([]);
  });

  // The scenario's other half: switched on, the page is listed.
  acceptance("web-ui", "the palette leaves out switched-off features", async () => {
    features = { fake_feature: true };
    renderPalette();
    await settled();
    type("fake page");
    expect(options()).toEqual(["Fake page"]);
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
    expect(within(group("Pages")).getAllByRole("option")).toHaveLength(20);
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
    expect(within(group("Pages")).getAllByRole("option")).toHaveLength(20);
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
