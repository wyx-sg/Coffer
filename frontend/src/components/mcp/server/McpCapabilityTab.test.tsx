// src/components/mcp/server/McpCapabilityTab.test.tsx — the Resources and Prompts tabs list everything the server offers (spec mcp-gateway "Forward tools, resources and prompts").
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
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

let observed: { callback: IntersectionObserverCallback }[] = [];
beforeEach(() => {
  observed = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: IntersectionObserverCallback) {
        observed.push({ callback });
      }
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("McpCapabilityTab", () => {
  test("a short list shows every resource, with no footer and no button", () => {
    renderTab("resource", 3);
    expect(rowCount()).toBe(3);
    expect(screen.queryByText(/^Showing/)).toBeNull();
    expect(screen.queryByRole("button", { name: /more/i })).toBeNull();
  });

  test("the toolbar counts what is on, and Prompts says where they show up", () => {
    renderTab("prompt", 4);
    expect(screen.getByTestId("mcp-caps-on")).toHaveTextContent(/\d+ of 4 on/);
    expect(screen.getByText(/slash-command menu/)).toBeInTheDocument();
  });

  acceptance("mcp-gateway", "a server's resources and prompts are listed in full", () => {
    renderTab("prompt", 120);
    // The first 100 render; the rest are added when the end scrolls into view.
    expect(rowCount()).toBe(100);
    act(() =>
      observed
        .at(-1)
        ?.callback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          {} as IntersectionObserver,
        ),
    );
    expect(rowCount()).toBe(120);

    fireEvent.change(screen.getByRole("textbox", { name: "Search prompts" }), {
      target: { value: "p119" },
    });
    expect(rowCount()).toBe(1);
  });
});
