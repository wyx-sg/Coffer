// src/components/mcp/server/McpServerList.test.tsx — the MCP servers list column: filter rows, hover checkboxes, the selection bar at the top, and the built-in group obeying the filters.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { ResourceOut } from "@/lib/api/resources";
import { McpServerList } from "./McpServerList";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));
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

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter>
            <McpServerList
              servers={SERVERS}
              isLoading={false}
              selectedName={null}
              hrefFor={(n) => `/mcp-servers/${n}`}
            />
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
    builtin.data = { name: "coffer", url: "http://127.0.0.1:8000/mcp", tool_count: 2 };
  });

  test("the search has its own row and Reach sits on the next, labelled in the trigger", () => {
    renderList();
    const search = screen.getByRole("textbox", { name: "Filter servers" });
    const reach = screen.getByRole("combobox", { name: "Reach" });
    const row = reach.parentElement?.parentElement;
    expect(row?.contains(search)).toBe(false);
    expect(reach).toHaveTextContent("Reach: All");
    expect(screen.queryByRole("combobox", { name: "Kind" })).toBeNull();
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

  test("ticking a row puts the selection bar at the top with an indeterminate select-all", () => {
    renderList();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: github/ }));
    const bar = screen.getByRole("region", { name: "Selected MCP servers" });
    expect(screen.queryByRole("textbox", { name: "Filter servers" })).toBeNull();
    const all = within(bar).getByRole("checkbox", {
      name: "Select all shown servers",
    }) as HTMLInputElement;
    expect(all.indeterminate).toBe(true);
    fireEvent.click(all);
    expect(within(bar).getByText("2 selected")).toBeInTheDocument();
    expect(all.checked).toBe(true);
    fireEvent.click(within(bar).getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("region", { name: "Selected MCP servers" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Filter servers" })).toBeInTheDocument();
  });

  test("the built-in server has no checkbox and select-all leaves it out", () => {
    renderList();
    const group = screen.getByRole("region", { name: "Built-in" });
    expect(within(group).queryByRole("checkbox")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: github/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all shown servers" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
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
