// src/components/mcp/server/McpServerList.test.tsx — the MCP servers list column: the search, hover checkboxes, the selection bar at the top, groups in order, and the built-in group obeying the search.
import { useState } from "react";
import { acceptance } from "@/test/acceptance";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { ResourceOut } from "@/lib/api/resources";
import { McpServerList } from "./McpServerList";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({
    data: [
      { uid: "u-cc", type: "claude_code", name: "claude_code" },
      { uid: "u-cx", type: "codex", name: "codex" },
    ],
  }),
}));
vi.mock("@/lib/hooks/useMcpServerPage", () => ({
  useMcpServerListReads: () => ({ details: new Map(), splits: new Map() }),
}));
const builtin: { data: unknown } = { data: undefined };
vi.mock("@/lib/hooks/useMcpAddFlow", () => ({
  useBuiltinMcpServer: () => ({ data: builtin.data }),
}));

function server(uid: string, name: string, extra: Partial<ResourceOut> = {}): ResourceOut {
  return {
    uid,
    name,
    kind: "mcp_server",
    title: null,
    enabled: true,
    scope: null,
    config: { transport: { type: "stdio", command: "npx", args: ["-y", name] } },
    ...extra,
  } as unknown as ResourceOut;
}

const SERVERS = [server("u-gh", "github"), server("u-ln", "linear", { enabled: false })];

function Harness({ servers }: { servers: ResourceOut[] }) {
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  return (
    <McpServerList
      servers={servers}
      isLoading={false}
      selectedName={null}
      hrefFor={(n) => `/mcp-servers/${n}`}
      picked={picked}
      onPickedChange={setPicked}
    />
  );
}

function renderList(servers: ResourceOut[] = SERVERS, path = "/mcp-servers") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[path]}>
            <Harness servers={servers} />
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** The wrapper that carries a row's checkbox: hidden unless hovered, focused or selecting. */
const checkboxSlot = (box: HTMLElement) => box.parentElement?.parentElement as HTMLElement;

describe("McpServerList", () => {
  beforeEach(() => {
    builtin.data = { name: "coffer", url: "http://127.0.0.1:38470/mcp", tool_count: 2 };
  });

  acceptance("web-ui", "the Reach filter narrows the servers to one agent", async () => {
    renderList([
      server("u-gh", "github"),
      server("u-cx", "codex-only", { scope: { agents: ["u-cx"] } as ResourceOut["scope"] }),
    ]);
    expect(screen.getByRole("textbox", { name: "Filter servers" })).toBeInTheDocument();
    const reach = screen.getByRole("combobox", { name: "Reach" });
    expect(reach).toHaveTextContent("All");
    // Radix Select opens from the keyboard in jsdom (no PointerEvent).
    fireEvent.keyDown(reach, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "Claude Code" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: /codex-only/ })).toBeNull());
    expect(screen.getByRole("link", { name: /github/ })).toBeInTheDocument();
    // Coffer's own server reaches every agent, so it stays.
    expect(screen.getByRole("link", { name: /coffer/ })).toBeInTheDocument();
  });

  test("the groups read Off after Healthy, and an off server leaves its Reach column empty", () => {
    renderList();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings.indexOf("Healthy")).toBeLessThan(headings.indexOf("Off"));
    const off = screen.getByRole("link", { name: /linear/ });
    expect(within(off).queryByText("Off")).toBeNull();
    expect(within(off).queryByText("All agents")).toBeNull();
    expect(
      within(screen.getByRole("link", { name: /github/ })).getByText("All agents"),
    ).toBeInTheDocument();
  });

  test("a row's checkbox shows on hover or focus only, and on every row once any is ticked", () => {
    renderList();
    const box = screen.getByRole("checkbox", { name: /Select row: github/ });
    expect(checkboxSlot(box).className).toContain("hidden");
    expect(checkboxSlot(box).className).toContain("group-hover:inline-flex");
    fireEvent.click(box);
    const other = screen.getByRole("checkbox", { name: /Select row: linear/ });
    expect(checkboxSlot(other).className).not.toContain("hidden");
  });

  acceptance("web-ui", "ticking a server puts the selection bar at the top", () => {
    renderList();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: github/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: linear/ }));
    const bar = screen.getByRole("region", { name: "Selected MCP servers" });
    expect(screen.queryByRole("textbox", { name: "Filter servers" })).toBeNull();
    expect(within(bar).getByText("2 of 2 selected")).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: /Reach/ })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(within(bar).queryByRole("checkbox")).toBeNull();
    fireEvent.click(within(bar).getByRole("button", { name: "Clear selection" }));
    expect(screen.queryByRole("region", { name: "Selected MCP servers" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Filter servers" })).toBeInTheDocument();
  });

  test("a select-all row appears once a row is ticked and ticks every listed row, not the built-in one", () => {
    renderList();
    expect(screen.queryByRole("checkbox", { name: "Select all" })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: github/ }));
    const all = screen.getByRole("checkbox", { name: "Select all" }) as HTMLInputElement;
    expect(all.indeterminate).toBe(true);
    fireEvent.click(all);
    expect(screen.getByText("2 of 2 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all" }));
    expect(screen.queryByRole("region", { name: "Selected MCP servers" })).toBeNull();
  });

  test("the built-in server has no checkbox and is not counted; Esc clears the selection", () => {
    renderList();
    const group = screen.getByRole("region", { name: "Built-in" });
    expect(within(group).queryByRole("checkbox")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: github/ }));
    expect(screen.getByText("1 of 2 selected")).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Selected MCP servers" })).toBeNull();
  });

  test("the search hides the built-in group when it does not match", () => {
    renderList();
    const search = screen.getByRole("textbox", { name: "Filter servers" });
    fireEvent.change(search, { target: { value: "git" } });
    expect(screen.queryByRole("region", { name: "Built-in" })).toBeNull();
    fireEvent.change(search, { target: { value: "coff" } });
    expect(screen.getByRole("region", { name: "Built-in" })).toBeInTheDocument();
    expect(screen.queryByText("github")).toBeNull();
  });
});

describe("McpServerList row click", () => {
  test("a click on a row opens the server; its checkbox does not", () => {
    renderList();
    const link = screen.getByRole("link", { name: /github/ });
    const opened = vi.fn((e: Event) => e.preventDefault());
    link.addEventListener("click", opened);
    fireEvent.click(link.closest("li")!);
    expect(opened).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: github/ }));
    expect(opened).toHaveBeenCalledTimes(1);
  });
});
