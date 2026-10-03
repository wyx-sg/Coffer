// src/components/mcp/server/McpCapabilityTab.test.tsx — the Resources and Prompts tabs list everything the server offers (spec mcp-gateway "Forward tools, resources and prompts").
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { McpCapabilityTab } from "./McpCapabilityTab";

function renderTab(kind: "resource" | "prompt", count: number) {
  const caps = {
    server_name: "smart",
    tools: [],
    resources: Array.from({ length: kind === "resource" ? count : 0 }, (_, i) => ({
      prefixed_uri: `smart__file:///r${i}`,
      original_uri: `file:///r${i}`,
      name: `r${i}`,
      description: `resource ${i}`,
      enabled: true,
    })),
    prompts: Array.from({ length: kind === "prompt" ? count : 0 }, (_, i) => ({
      prefixed_name: `smart__p${i}`,
      original_name: `p${i}`,
      description: `prompt ${i}`,
      arguments: [],
      enabled: true,
    })),
    fetched_at: "",
    from_cache: false,
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <McpCapabilityTab
            serverUid="u-smart"
            kind={kind}
            capabilities={caps as never}
            pending={false}
            error={null}
            summary={undefined}
          />
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const rowCount = () => within(screen.getByRole("table")).getAllByRole("row").length - 1;

describe("McpCapabilityTab", () => {
  test("a short list shows every resource, with its footer and no Show more", () => {
    renderTab("resource", 3);
    expect(rowCount()).toBe(3);
    expect(screen.getByTestId("mcp-caps-shown")).toHaveTextContent("Showing 3 of 3");
    expect(screen.queryByRole("button", { name: /Show \d+ more/ })).toBeNull();
  });

  acceptance("mcp-gateway", "resources forward through the gateway", () => {
    renderTab("prompt", 120);
    expect(rowCount()).toBe(50);
    fireEvent.click(screen.getByRole("button", { name: "Show 50 more" }));
    fireEvent.click(screen.getByRole("button", { name: "Show 20 more" }));
    expect(rowCount()).toBe(120);
    expect(screen.getByTestId("mcp-caps-shown")).toHaveTextContent("Showing 120 of 120");

    fireEvent.change(screen.getByRole("textbox", { name: "Search" }), {
      target: { value: "p119" },
    });
    expect(rowCount()).toBe(1);
  });
});
