// frontend/src/kinds/mcp/CapabilityList.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CapabilityList } from "./CapabilityList";
import { ApiError } from "@/lib/api/errors";
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

// Open the status filter dropdown and click an option by its label. DataTable
// renders the filter combobox in its toolbar (first in DOM order) and the
// pagination page-size combobox after the table, so the status filter is the
// first combobox.
function selectStatus(optionName: string) {
  const trigger = screen.getAllByRole("combobox")[0];
  fireEvent.click(trigger);
  const option = screen.getByRole("option", { name: optionName });
  fireEvent.click(option);
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

  test("renders selection checkboxes when there are rows", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    // Select-all header checkbox + one per row — at least one must render so
    // the bulk Enable/Disable flow is reachable.
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(1);
  });

  test("shows empty state when no items", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={[]} />));

    expect(screen.getByText(/No tools discovered/)).toBeInTheDocument();
  });

  test("expands schema JSON when a tool row is clicked", async () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    const row = screen.getByText("read_file").closest("tr")!;
    fireEvent.click(row);

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

  test("Resource tab: empty state keeps the search/filter chrome (consistent with Tools)", () => {
    render(wrap(<CapabilityList serverName="fs" kind="resource" resources={[]} />));
    // The empty copy renders inside the table, and the search box is still
    // present so an empty Resources tab looks like the Tools tab.
    expect(screen.getByText(/No resources discovered/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search by name")).toBeInTheDocument();
  });

  test("Prompt tab: empty state keeps the search/filter chrome (consistent with Tools)", () => {
    render(wrap(<CapabilityList serverName="fs" kind="prompt" prompts={[]} />));
    expect(screen.getByText(/No prompts discovered/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search by name")).toBeInTheDocument();
  });

  test("shows an upstream-error state instead of the empty copy when the capability fetch failed", () => {
    // When /capabilities errors (e.g. the upstream connection is down), the
    // prompts list is undefined — the same shape as a genuinely empty upstream.
    // The two must read differently: a failed fetch must NOT claim "no prompts
    // discovered" (which wrongly implies the upstream has none).
    const err = new ApiError("UPSTREAM_UNAVAILABLE", "upstream down");
    render(wrap(<CapabilityList serverName="fs" kind="prompt" prompts={undefined} error={err} />));

    expect(screen.getByText(/Couldn't load/i)).toBeInTheDocument();
    expect(screen.queryByText(/No prompts discovered/)).not.toBeInTheDocument();
  });

  // ── Search + filter tests ────────────────────────────────────────────────

  test("search box filters capabilities by name (case-insensitive)", async () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    const searchInput = screen.getByPlaceholderText("Search by name");
    fireEvent.change(searchInput, { target: { value: "READ" } });

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.queryByText("write_file")).not.toBeInTheDocument();
  });

  test("status filter set to 'disabled' shows only disabled capabilities", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    selectStatus("Disabled");

    // Only the disabled tool should remain
    expect(screen.queryByText("read_file")).not.toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();
  });

  test("status filter set to 'enabled' shows only enabled capabilities", () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    selectStatus("Enabled");

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

    selectStatus("Disabled");

    expect(screen.getByText(/No capabilities match/i)).toBeInTheDocument();
    expect(screen.queryByText(/No tools discovered/)).not.toBeInTheDocument();
  });

  test("toggling a switch does not expand the row's schema detail", async () => {
    render(wrap(<CapabilityList serverName="fs" kind="tool" tools={sampleTools} />));

    const row = screen.getByText("read_file").closest("tr")!;
    const toggle = within(row).getByRole("switch");
    fireEvent.click(toggle);

    // The switch stops propagation, so the row detail must NOT open.
    expect(screen.queryByText(/"type": "object"/)).not.toBeInTheDocument();
  });
});
