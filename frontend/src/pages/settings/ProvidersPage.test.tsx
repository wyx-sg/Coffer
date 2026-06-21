// pages/settings/ProvidersPage.test.tsx
import { beforeEach, describe, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { acceptance } from "@/test/acceptance";
import { ProvidersPage } from "./ProvidersPage";
import type { Provider } from "@/lib/api/providers";

vi.mock("@/lib/api/providers", () => ({
  providersApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    activate: vi.fn(),
  },
}));

const { providersApi } = await import("@/lib/api/providers");
const apiMock = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const makeProvider = (overrides?: Partial<Provider>): Provider => ({
  name: "acme",
  wire_format: "anthropic",
  base_url: "https://gw/anthropic",
  credential_ref: "provider/acme/key",
  model: "claude-opus-4-8",
  fast_model: null,
  wire_api: "chat",
  is_active: false,
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ProvidersPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ProvidersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  acceptance(
    "011-provider-switching",
    "the Providers page lists profiles and can switch the active one",
    async () => {
      apiMock.list.mockResolvedValue({
        providers: [
          makeProvider({ name: "official", is_active: true }),
          makeProvider({ name: "kimi", is_active: false }),
        ],
      });
      apiMock.activate.mockResolvedValue({
        activated: "kimi",
        wire_format: "anthropic",
        projected: ["cc"],
        skipped: [],
      });

      renderPage();

      // lists the profiles
      expect(await screen.findByText("official")).toBeInTheDocument();
      expect(screen.getByText("kimi")).toBeInTheDocument();

      // the active one is marked and cannot be re-switched; the inactive one can
      const switchButtons = screen.getAllByRole("button", { name: "Switch" });
      expect(switchButtons).toHaveLength(1); // only "kimi" (official is active)
      fireEvent.click(switchButtons[0]);

      await waitFor(() => expect(apiMock.activate).toHaveBeenCalledWith("kimi"));
    },
  );
});
