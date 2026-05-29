// frontend/src/kinds/mcp/CapabilityList.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CapabilityList } from "./CapabilityList";
import type { components } from "@/lib/api/types";

type MCPResourceView = components["schemas"]["MCPResourceView"];
type MCPPromptView = components["schemas"]["MCPPromptView"];

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const sampleTools = [
  {
    original_name: "read_file",
    prefixed_name: "fs__read_file",
    description: "Read a file from disk",
    enabled: true,
    input_schema: { type: "object", properties: { path: { type: "string" } } },
  },
  {
    original_name: "write_file",
    prefixed_name: "fs__write_file",
    description: null,
    enabled: false,
    input_schema: undefined,
  },
];

describe("CapabilityList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getApiClientMock.mockReturnValue({
      POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);
  });

  test("renders tool rows with name, prefixed name, and description", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("fs__read_file")).toBeInTheDocument();
    expect(screen.getByText("Read a file from disk")).toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();
    expect(screen.getByText("fs__write_file")).toBeInTheDocument();
  });

  test("shows empty state when no items", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={[]} />));

    expect(screen.getByText(/No tools discovered/)).toBeInTheDocument();
  });

  test("expands schema JSON when expand button is clicked on a tool with schema", async () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    const expandBtn = screen.getByRole("button", { name: "Expand schema" });
    fireEvent.click(expandBtn);

    await waitFor(() => {
      expect(screen.getByText(/"type": "object"/)).toBeInTheDocument();
    });
  });

  test("toggle switch calls enable mutation when switching from disabled to enabled", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={[{ ...sampleTools[1] }]} />));

    // write_file is disabled (enabled: false) — toggling it should call enable
    const toggle = screen.getByRole("switch", { name: /Toggle tool write_file/ });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/resources/mcp_server/{name}/capabilities/{capability_type}/enable",
        expect.objectContaining({
          params: { path: { name: "fs", capability_type: "tool" } },
          body: { capability_key: "write_file" },
        }),
      );
    });
  });

  test("Resource tab: renders resource row and calls disable when toggled off", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    const sampleResources: MCPResourceView[] = [
      {
        original_uri: "file:///data",
        prefixed_uri: "fs__file:///data",
        description: "Data directory",
        enabled: true,
        mime_type: null,
      },
    ];

    render(wrap(<CapabilityList serverName="fs" kind="resource" resources={sampleResources} />));

    expect(screen.getByText("file:///data")).toBeInTheDocument();
    expect(screen.getByText("fs__file:///data")).toBeInTheDocument();
    expect(screen.getByText("Data directory")).toBeInTheDocument();

    // Toggle from enabled → disabled
    const toggle = screen.getByRole("switch", { name: /Toggle resource file:\/\/\/data/ });
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/resources/mcp_server/{name}/capabilities/{capability_type}/disable",
        expect.objectContaining({
          params: { path: { name: "fs", capability_type: "resource" } },
          body: { capability_key: "file:///data" },
        }),
      );
    });
  });

  test("Prompt tab: renders prompt row and calls enable when toggled on", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    const samplePrompts: MCPPromptView[] = [
      {
        original_name: "summarize",
        prefixed_name: "fs__summarize",
        description: "Summarize a file",
        enabled: false,
      },
    ];

    render(wrap(<CapabilityList serverName="fs" kind="prompt" prompts={samplePrompts} />));

    expect(screen.getByText("summarize")).toBeInTheDocument();
    expect(screen.getByText("fs__summarize")).toBeInTheDocument();
    expect(screen.getByText("Summarize a file")).toBeInTheDocument();

    // Toggle from disabled → enabled
    const toggle = screen.getByRole("switch", { name: /Toggle prompt summarize/ });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/resources/mcp_server/{name}/capabilities/{capability_type}/enable",
        expect.objectContaining({
          params: { path: { name: "fs", capability_type: "prompt" } },
          body: { capability_key: "summarize" },
        }),
      );
    });
  });

  test("Resource tab: shows empty state when no resources", () => {
    render(wrap(<CapabilityList serverName="fs" kind="resource" resources={[]} />));
    expect(screen.getByText(/No resources discovered/)).toBeInTheDocument();
  });

  test("Prompt tab: shows empty state when no prompts", () => {
    render(wrap(<CapabilityList serverName="fs" kind="prompt" prompts={[]} />));
    expect(screen.getByText(/No prompts discovered/)).toBeInTheDocument();
  });

  // ── Search + filter tests ────────────────────────────────────────────────

  test("search box filters capabilities by name (case-insensitive)", async () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    const searchInput = screen.getByPlaceholderText("Search by name");
    fireEvent.change(searchInput, { target: { value: "READ" } });

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.queryByText("write_file")).not.toBeInTheDocument();
  });

  test("enabled filter set to 'disabled' shows only disabled capabilities", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    // Open the status select and pick "Disabled"
    const trigger = screen.getByRole("combobox", { name: /status/i });
    fireEvent.click(trigger);
    const disabledOption = screen.getByRole("option", { name: "Disabled" });
    fireEvent.click(disabledOption);

    // Only the disabled tool should remain
    expect(screen.queryByText("read_file")).not.toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();
  });

  test("enabled filter set to 'enabled' shows only enabled capabilities", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    const trigger = screen.getByRole("combobox", { name: /status/i });
    fireEvent.click(trigger);
    const enabledOption = screen.getByRole("option", { name: "Enabled" });
    fireEvent.click(enabledOption);

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.queryByText("write_file")).not.toBeInTheDocument();
  });

  test("shows 'no matches' message when search excludes all capabilities", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    const searchInput = screen.getByPlaceholderText("Search by name");
    fireEvent.change(searchInput, { target: { value: "zzznomatch" } });

    // 'No matches' message should appear
    expect(screen.getByText(/No capabilities match/i)).toBeInTheDocument();
    // The regular empty state should NOT appear (capabilities exist, just filtered)
    expect(screen.queryByText(/No tools discovered/)).not.toBeInTheDocument();
  });

  test("shows 'no matches' message when filter excludes all capabilities (all enabled)", () => {
    const allEnabledTools = sampleTools.map((t) => ({ ...t, enabled: true }));
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={allEnabledTools} />));

    const trigger = screen.getByRole("combobox", { name: /status/i });
    fireEvent.click(trigger);
    const disabledOption = screen.getByRole("option", { name: "Disabled" });
    fireEvent.click(disabledOption);

    expect(screen.getByText(/No capabilities match/i)).toBeInTheDocument();
    expect(screen.queryByText(/No tools discovered/)).not.toBeInTheDocument();
  });
});
