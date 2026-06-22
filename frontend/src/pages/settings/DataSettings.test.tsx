// frontend/src/pages/settings/DataSettings.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

  test("renders the backup action alongside retention", async () => {
    mockPolicies(MOCK_POLICIES);
    render(wrap(<DataSettings />));

    await screen.findByText("Audit log");
    expect(screen.getByRole("button", { name: /create backup/i })).toBeInTheDocument();
  });

  test("days input hidden when 'keep forever' is toggled on", async () => {
    mockPolicies([MOCK_POLICIES[0]]);
    render(wrap(<DataSettings />));

    await screen.findByText("Audit log");
    expect(screen.getByLabelText("Retention (days)")).toBeInTheDocument();

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

    const daysInput = screen.getByLabelText("Retention (days)");
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
