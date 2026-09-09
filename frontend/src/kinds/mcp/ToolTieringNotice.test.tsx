// frontend/src/kinds/mcp/ToolTieringNotice.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToolTieringNotice } from "./ToolTieringNotice";

const mockGet = vi.fn();

vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({ GET: mockGet }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key}:${JSON.stringify(vars)}` : key,
  }),
}));

function renderNotice() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToolTieringNotice />
    </QueryClientProvider>,
  );
}

describe("ToolTieringNotice", () => {
  beforeEach(() => mockGet.mockReset());

  it("reports the split when tiering is hiding tools", async () => {
    mockGet.mockResolvedValue({
      data: { enabled: true, budget: 50, window_days: 90, total: 125, listed: 50, hidden: 75, servers: [] },
    });

    renderNotice();

    await waitFor(() =>
      expect(screen.getByTestId("tool-tiering-notice")).toHaveTextContent(/"hidden":75/),
    );
  });

  it("stays out of the way when nothing is hidden", async () => {
    mockGet.mockResolvedValue({
      data: { enabled: true, budget: 50, window_days: 90, total: 20, listed: 20, hidden: 0, servers: [] },
    });

    renderNotice();

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(screen.queryByTestId("tool-tiering-notice")).toBeNull();
  });

  it("renders nothing when tiering is switched off", async () => {
    mockGet.mockResolvedValue({
      data: { enabled: false, budget: 50, window_days: 90, total: 125, listed: 125, hidden: 0, servers: [] },
    });

    renderNotice();

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(screen.queryByTestId("tool-tiering-notice")).toBeNull();
  });
});
