// frontend/src/components/mcp/McpServerTitle.test.tsx
//
// An MCP server's title (spec web-ui "Show and edit a title on MCP server and
// skill pages"): set on the detail page through the edit dialog, then shown in
// place of the name on the detail header and the list row, each with the name
// beside it — the name being what an agent sees and fixed after registration.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { acceptance } from "@/test/acceptance";
import type { ResourceOut } from "@/lib/api/resources";
import { McpServerDetailHeader } from "./McpServerDetailHeader";
import { McpServersTable } from "./McpServersTable";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
vi.mock("@/lib/hooks/useMcpServerStatus", () => ({
  useMcpServerStatus: vi.fn(() => ({ data: "healthy" })),
  useMcpServerRunner: vi.fn(() => ({ data: { missingRunner: null } })),
}));

const { getApiClient } = await import("@/lib/api/client");

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const server = (over: Partial<ResourceOut> = {}): ResourceOut => ({
  uid: "u-search",
  kind: "mcp_server",
  name: "srch",
  title: null,
  enabled: true,
  scope: null,
  description: "Search",
  config: { transport: { type: "stdio", command: "npx" } },
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  ...over,
});

const OTHER = server({ uid: "u-files", name: "files", description: "Files" });

function header(resource: ResourceOut) {
  return (
    <McpServerDetailHeader
      resource={resource}
      back={{ to: "/mcp-servers", label: "MCP servers" }}
      healthState="healthy"
      testResult={null}
      isTestPending={false}
      onTestConnection={vi.fn()}
      onDeleteClick={vi.fn()}
    />
  );
}

describe("MCP server title", () => {
  acceptance("web-ui", "a titled server is listed and headed by its title", async () => {
    const patch = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    vi.mocked(getApiClient).mockReturnValue({
      PATCH: patch,
      POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    // The user sets the title on the detail page. The edit form shows the name
    // as fixed — read-only text with the note, never an input.
    const { unmount } = render(wrap(header(server())));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/^srch$/);
    expect(screen.getByText("Fixed name")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("textbox", { name: /^name$/i })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("group", { name: /^name$/i })).toHaveTextContent("srch");
    expect(within(dialog).getByText(/cannot change after registration/i)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Title"), {
      target: { value: "Team search" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /save/i }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch.mock.calls[0][1].params.path.uid).toBe("u-search");
    expect(patch.mock.calls[0][1].body.title).toBe("Team search");
    unmount();

    // The detail header shows the title, with the name beside it.
    const titled = server({ title: "Team search" });
    const { unmount: unmountHeader } = render(wrap(header(titled)));
    const heading = screen.getByRole("heading", { level: 1 });
    expect(within(heading).getByText("Team search")).toBeInTheDocument();
    expect(within(heading).getByText("srch")).toBeInTheDocument();
    unmountHeader();

    // The list row shows the same, and the search finds it by its NAME.
    render(wrap(<McpServersTable resources={[titled, OTHER]} />));
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "srch" } });
    const row = screen.getByText("Team search").closest("tr") as HTMLElement;
    expect(within(row).getByText("srch")).toBeInTheDocument();
    expect(screen.queryByText("files")).not.toBeInTheDocument();
  });

  test("an untitled row shows its name alone", () => {
    render(wrap(<McpServersTable resources={[OTHER]} />));
    const row = screen.getByText("files").closest("tr") as HTMLElement;
    expect(row.querySelector('[data-slot="resource-name"]')).toBeNull();
  });

  test("saving other fields sends no title change", async () => {
    const patch = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    vi.mocked(getApiClient).mockReturnValue({
      PATCH: patch,
      POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);
    render(wrap(header(server({ title: "Team search" }))));
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /save/i }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect("title" in patch.mock.calls[0][1].body).toBe(false);
  });
});
