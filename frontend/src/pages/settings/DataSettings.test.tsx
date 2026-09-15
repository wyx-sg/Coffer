// frontend/src/pages/settings/DataSettings.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataSettings } from "./DataSettings";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

const MOCK_POLICIES = [
  {
    table_name: "audit_log",
    display_name: "Audit log",
    description: "Tracks every lifecycle event.",
    default_retention_days: 90,
    retention_days: 30,
    last_pruned_at: null,
    last_pruned_rows: 0,
  },
  {
    table_name: "mcp_invocations",
    display_name: "MCP Invocations",
    description: "Tool call history.",
    default_retention_days: 30,
    retention_days: null,
    last_pruned_at: "2026-05-01T00:00:00Z",
    last_pruned_rows: 100,
  },
];

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function mockPolicies(
  policies: typeof MOCK_POLICIES,
  {
    patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined }),
    postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined }),
  }: {
    patchMock?: ReturnType<typeof vi.fn>;
    postMock?: ReturnType<typeof vi.fn>;
  } = {},
) {
  getApiClientMock.mockReturnValue({
    GET: vi.fn().mockResolvedValue({
      data: { policies },
      error: undefined,
    }),
    POST: postMock,
    PATCH: patchMock,
  } as unknown as ReturnType<typeof getApiClient>);
  return { patchMock, postMock };
}

describe("DataSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders all retention policy cards", async () => {
    mockPolicies(MOCK_POLICIES);
    render(wrap(<DataSettings />));

    expect(await screen.findByText("Data retention")).toBeInTheDocument();
    expect(screen.getByText("Audit log")).toBeInTheDocument();
    expect(screen.getByText("MCP invocations")).toBeInTheDocument();
  });

  test("days input hidden when 'keep forever' is toggled on", async () => {
    mockPolicies([MOCK_POLICIES[0]]);
    render(wrap(<DataSettings />));

    await screen.findByText("Audit log");
    expect(screen.getByLabelText("Keep for (days)")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Keep forever"));
    expect(screen.queryByLabelText("Retention (days)")).not.toBeInTheDocument();
  });

  test("auto-saves: no Save button — retention persists on edit", async () => {
    mockPolicies([MOCK_POLICIES[0]]);
    render(wrap(<DataSettings />));

    await screen.findByText("Audit log");
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  test("editing days and blurring auto-saves the PATCH", async () => {
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    mockPolicies([MOCK_POLICIES[0]], { patchMock });

    render(wrap(<DataSettings />));
    await screen.findByText("Audit log");

    const daysInput = screen.getByLabelText("Keep for (days)");
    fireEvent.change(daysInput, { target: { value: "90" } });
    fireEvent.blur(daysInput);

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith(
        "/retention/policies/{table_name}",
        expect.objectContaining({
          params: { path: { table_name: "audit_log" } },
          body: { retention_days: 90 },
        }),
      );
    });
  });

  test("clearing expired data asks first, then reports rows per policy by its display name", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: { tables: { audit_log: 12, mcp_invocations: 0 } },
      error: undefined,
    });
    mockPolicies(MOCK_POLICIES, { postMock });
    render(wrap(<DataSettings />));
    await screen.findByText("Audit log");

    fireEvent.click(screen.getByRole("button", { name: "Clear expired data now" }));
    expect(postMock).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Clear expired data now?");
    fireEvent.click(within(dialog).getByRole("button", { name: "Clear expired data now" }));

    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/retention/prune", { body: {} }));
    // Named the way the rows are, never by table name; zero-row tables are left out.
    expect(await screen.findByRole("status")).toHaveTextContent("Removed 12 rows from Audit log");
    expect(screen.getByRole("status")).not.toHaveTextContent("audit_log");
    expect(screen.getByRole("status")).not.toHaveTextContent("MCP invocations");
  });

  test("a prune that removed nothing says so", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: { tables: {} }, error: undefined });
    mockPolicies([MOCK_POLICIES[0]], { postMock });
    render(wrap(<DataSettings />));
    await screen.findByText("Audit log");

    fireEvent.click(screen.getByRole("button", { name: "Clear expired data now" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Clear expired data now" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Nothing to clear");
  });

  test("toggling 'keep forever' auto-saves retention_days: null", async () => {
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    mockPolicies([MOCK_POLICIES[0]], { patchMock });

    render(wrap(<DataSettings />));
    await screen.findByText("Audit log");

    fireEvent.click(screen.getByLabelText("Keep forever"));

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith(
        "/retention/policies/{table_name}",
        expect.objectContaining({
          params: { path: { table_name: "audit_log" } },
          body: { retention_days: null },
        }),
      );
    });
  });
});
