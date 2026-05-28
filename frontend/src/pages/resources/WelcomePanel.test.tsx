// frontend/src/pages/resources/WelcomePanel.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { WelcomePanel } from "./WelcomePanel";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WelcomePanel", () => {
  test("renders the onboarding title", () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<WelcomePanel />));
    // The welcome card title contains the vault description
    expect(screen.getByRole("heading", { name: /local-first vault/i })).toBeInTheDocument();
  });

  test("renders the 'Add MCP server' CTA button", () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<WelcomePanel />));
    expect(screen.getByRole("button", { name: /add mcp server/i })).toBeInTheDocument();
  });

  test("renders three feature highlight items", () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<WelcomePanel />));
    // Exactly three feature li items (featureAggregate, featureCurate, featureLocal)
    const listItems = screen.getAllByRole("listitem");
    expect(listItems).toHaveLength(3);
  });
});
