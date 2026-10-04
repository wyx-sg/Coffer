// src/components/mcp/server/McpToolsTab.test.tsx — the Tools tab loads every tool and sets how each is exposed to agents (spec mcp-gateway "Choose how each tool is exposed").
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import type { ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { McpToolsTab } from "./McpToolsTab";
import type { ServerState } from "@/lib/mcp/serverState";

const api = vi.hoisted(() => ({ setToolExposure: vi.fn(async () => undefined) }));

vi.mock("@/lib/api/mcpServers", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/mcpServers")>()),
  mcpServersApi: {
    ...(await orig<typeof import("@/lib/api/mcpServers")>()).mcpServersApi,
    setToolExposure: api.setToolExposure,
  },
}));

const STATE = { kind: "healthy", group: "working" } as unknown as ServerState;

function tool(i: number) {
  const name = `tool_${String(i).padStart(2, "0")}`;
  return {
    prefixed_name: `smart__${name}`,
    original_name: name,
    description: `does ${name}`,
    input_schema: {},
    enabled: true,
    client_name_length: 20,
  };
}

const TOOLS = Array.from({ length: 78 }, (_, i) => tool(i));

function tiering(over: Partial<ToolTiering> = {}): ToolTiering {
  return {
    enabled: true,
    budget: 50,
    catalogue_size: 78,
    listed_count: 50,
    tool_count: 78,
    listed: [],
    behind_search: [],
    tools: TOOLS.map((t, i) => ({
      tool: t.original_name,
      mode: "auto",
      effective: i < 50 ? "listed" : "search",
      reason: i < 50 ? "top_by_use" : "low_use",
    })),
    ...over,
  } as ToolTiering;
}

function renderTab(tieringValue: ToolTiering | null = tiering()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter>
            <McpToolsTab
              serverUid="u-smart"
              state={STATE}
              detail={null}
              capabilities={
                {
                  server_name: "smart",
                  tools: TOOLS,
                  resources: [],
                  prompts: [],
                  fetched_at: "",
                  from_cache: false,
                } as never
              }
              pending={false}
              error={null}
              summary={undefined}
              tiering={tieringValue}
            />
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const rowCount = () => within(screen.getByRole("table")).getAllByRole("row").length - 1;

describe("McpToolsTab", () => {
  beforeEach(() => vi.clearAllMocks());

  acceptance("mcp-gateway", "a server's Tools tab lists every tool", () => {
    renderTab();
    expect(rowCount()).toBe(50);
    expect(screen.getByTestId("mcp-tools-shown")).toHaveTextContent("Showing 50 of 78");

    fireEvent.click(screen.getByRole("button", { name: "Show 28 more" }));
    expect(rowCount()).toBe(78);
    expect(screen.getByTestId("mcp-tools-shown")).toHaveTextContent("Showing 78 of 78");
    expect(screen.queryByRole("button", { name: /Show \d+ more/ })).toBeNull();
  });

  test("the search runs over all 78, not just the rows on screen", () => {
    renderTab();
    fireEvent.change(screen.getByRole("textbox", { name: "Search tools" }), {
      target: { value: "tool_77" },
    });
    expect(rowCount()).toBe(1);
    expect(screen.getByTestId("mcp-tools-shown")).toHaveTextContent("Showing 1 of 1");
  });

  acceptance("web-ui", "a search does not match descriptions", () => {
    renderTab();
    // Every description reads "does tool_NN"; "does" is in none of the names.
    fireEvent.change(screen.getByRole("textbox", { name: "Search tools" }), {
      target: { value: "does" },
    });
    expect(screen.queryByRole("table")).toBeNull();
  });

  acceptance("mcp-gateway", "a tool's exposure is chosen by the person", () => {
    renderTab();
    expect(screen.getByRole("combobox", { name: "Exposure of tool_00" })).toHaveTextContent(
      "Auto · Listed",
    );
    fireEvent.click(screen.getByRole("button", { name: "Show 28 more" }));
    expect(screen.getByRole("combobox", { name: "Exposure of tool_77" })).toHaveTextContent(
      "Auto · Behind search",
    );
  });

  test("a pinned and a search-only tool read as set", () => {
    const t = tiering();
    t.tools = t.tools.map((e) =>
      e.tool === "tool_00"
        ? { ...e, mode: "search", effective: "search", reason: "search_only" }
        : e.tool === "tool_01"
          ? { ...e, mode: "listed", effective: "listed", reason: "pinned" }
          : e,
    ) as ToolTiering["tools"];
    renderTab(t);
    expect(screen.getByRole("combobox", { name: "Exposure of tool_00" })).toHaveTextContent(
      "Search only",
    );
    expect(screen.getByRole("combobox", { name: "Exposure of tool_01" })).toHaveTextContent(
      "Always listed",
    );
  });

  test("choosing a mode calls the API for that tool", async () => {
    renderTab();
    const trigger = screen.getByRole("combobox", { name: "Exposure of tool_02" });
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.click(await screen.findByRole("option", { name: "Always listed" }));
    await waitFor(() =>
      expect(api.setToolExposure).toHaveBeenCalledWith("u-smart", ["tool_02"], "listed"),
    );
  });

  test("the toolbar menu sets the filtered tools in one call", async () => {
    renderTab();
    fireEvent.change(screen.getByRole("textbox", { name: "Search tools" }), {
      target: { value: "tool_1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Set exposure" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Set 10 to Search only" }));
    await waitFor(() => expect(api.setToolExposure).toHaveBeenCalledTimes(1));
    const [uid, tools, mode] = api.setToolExposure.mock.calls[0] as unknown as [
      string,
      string[],
      string,
    ];
    expect(uid).toBe("u-smart");
    expect(mode).toBe("search");
    expect(tools).toHaveLength(10);
    expect(tools[0]).toBe("tool_10");
  });

  test("with tiering off there is no exposure to set", () => {
    renderTab(tiering({ enabled: false }));
    expect(screen.queryByRole("combobox", { name: /Exposure of/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Set exposure" })).toBeNull();
  });
});
