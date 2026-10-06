// src/components/mcp/server/McpCapabilityRow.test.tsx — a resource or prompt row opens to its details and previews on demand (spec web-ui "Uniform capability tabs").
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { McpCapabilityTab } from "./McpCapabilityTab";

const api = vi.hoisted(() => ({
  readResource: vi.fn(),
  getPrompt: vi.fn(),
}));

vi.mock("@/lib/api/mcpServers", async (orig) => {
  const real = await orig<typeof import("@/lib/api/mcpServers")>();
  return { ...real, mcpServersApi: { ...real.mcpServersApi, ...api } };
});

const caps = {
  server_name: "smart",
  tools: [],
  resources: [
    {
      prefixed_uri: "smart__gateway://openapi.json",
      original_uri: "gateway://openapi.json",
      name: "openapi",
      description: "Generated OpenAPI document",
      mime_type: "application/json",
      enabled: true,
    },
  ],
  prompts: [
    {
      prefixed_name: "smart__review",
      original_name: "review",
      description: "Review a change",
      arguments: [
        { name: "diff", description: "The change to review", required: true },
        { name: "tone", description: null, required: false },
      ],
      enabled: true,
      client_name_length: 13,
    },
  ],
  fetched_at: "",
  from_cache: false,
};

function renderTab(kind: "resource" | "prompt") {
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

const openRow = (name: string) => fireEvent.click(screen.getByText(name));

describe("McpCapabilityRow", () => {
  acceptance("web-ui", "a resource row opens to its details and reads its content", async () => {
    api.readResource.mockResolvedValue({
      contents: [{ kind: "text", text: '{"openapi":"3.1.0"}', mime_type: "application/json" }],
    });
    renderTab("resource");
    expect(screen.queryByTestId("mcp-resource-detail")).toBeNull();
    openRow("gateway://openapi.json");
    const detail = screen.getByTestId("mcp-resource-detail");
    expect(detail).toHaveTextContent("application/json");
    expect(detail).toHaveTextContent("smart__gateway://openapi.json");
    // Nothing is read until asked.
    expect(api.readResource).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Read content" }));
    await waitFor(() =>
      expect(api.readResource).toHaveBeenCalledWith("u-smart", "gateway://openapi.json"),
    );
    // JSON is laid out for reading.
    expect(await screen.findByTestId("mcp-preview-text")).toHaveTextContent('"openapi": "3.1.0"');
    // The row closes again.
    openRow("gateway://openapi.json");
    expect(screen.queryByTestId("mcp-resource-detail")).toBeNull();
  });

  acceptance("web-ui", "a prompt row opens to its arguments and fills the prompt", async () => {
    api.getPrompt.mockResolvedValue({
      description: "Review a change",
      contents: [{ kind: "text", text: "Please review: +x", role: "user" }],
    });
    renderTab("prompt");
    openRow("review");
    const detail = screen.getByTestId("mcp-prompt-detail");
    expect(detail).toHaveTextContent("The change to review");
    expect(detail).toHaveTextContent("Required");
    const get = screen.getByRole("button", { name: "Get prompt" });
    expect(get).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "diff" }), { target: { value: "+x" } });
    fireEvent.click(get);
    await waitFor(() =>
      expect(api.getPrompt).toHaveBeenCalledWith("u-smart", "review", { diff: "+x" }),
    );
    expect(await screen.findByTestId("mcp-preview-result")).toHaveTextContent("User");
    expect(screen.getByTestId("mcp-preview-text")).toHaveTextContent("Please review: +x");
  });

  test("the server's own error reads in place of the content", async () => {
    api.readResource.mockResolvedValue({ contents: [], error: "unknown resource" });
    renderTab("resource");
    openRow("gateway://openapi.json");
    fireEvent.click(screen.getByRole("button", { name: "Read content" }));
    expect(
      await screen.findByText("The server answered with an error: unknown resource"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Read again" })).toBeEnabled();
  });

  test("a binary body is named by its type and size, never shown", async () => {
    api.readResource.mockResolvedValue({
      contents: [{ kind: "blob", text: null, size_bytes: 2048, mime_type: "image/png" }],
    });
    renderTab("resource");
    openRow("gateway://openapi.json");
    fireEvent.click(screen.getByRole("button", { name: "Read content" }));
    expect(
      await screen.findByText("Binary content (image/png, 2048 bytes), not shown."),
    ).toBeInTheDocument();
  });
});
