// frontend/src/pages/settings/EngineSettings.test.tsx
//
// Settings → Engine holds Coffer's own two engine configs: the internal LLM
// connection + model, and the embedding model. Both moved here off the
// model-provider page, which is now purely the connection library agents draw
// from — internal configuration is not a resource.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { acceptance } from "@/test/acceptance";
import { EngineSettings } from "./EngineSettings";
import type { Provider } from "@/lib/api/providers";

vi.mock("@/lib/api/providers", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/providers")>();
  return {
    ...actual,
    providersApi: {
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      activate: vi.fn(),
      setInternalDefault: vi.fn(),
    },
  };
});

// The internal-engine section reads/writes its own singleton config, and the
// model dropdown lists the chosen endpoint's models — both hit the network.
vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: { model: null, updated_at: null } }),
  useSetInternalEngineModel: () => ({ isPending: false, mutate: vi.fn() }),
}));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ isPending: false, mutate: vi.fn(), data: undefined }),
  useTestEmbedding: () => ({ isPending: false, mutate: vi.fn(), reset: vi.fn(), data: undefined }),
}));

// The embedding card owns its own config query; stub the hooks so the real
// card renders without a daemon behind it.
vi.mock("@/lib/hooks/useEmbeddingConfig", () => ({
  useEmbeddingConfig: () => ({
    data: {
      enabled: false,
      connection: null,
      model: null,
      dimensions: 768,
      default_chunk_size: 512,
      default_chunk_overlap: 64,
      updated_at: null,
    },
    isPending: false,
    error: null,
  }),
  useUpdateEmbeddingConfig: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useEmbeddingModels: () => ({ options: [], probing: false }),
}));

const { providersApi } = await import("@/lib/api/providers");
const apiMock = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const makeProvider = (overrides?: Partial<Provider>): Provider => ({
  name: "acme",
  protocol: "anthropic",
  base_url: "https://gw/anthropic",
  credential_ref: "provider/acme/key",
  compatible_agents: ["claude_code"],
  is_active: false,
  internal_default: false,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

// Radix Select: open via keyboard (jsdom has no pointer layout) then read/click
// the rendered options.
function openSelect(triggerName: RegExp) {
  fireEvent.keyDown(screen.getByRole("combobox", { name: triggerName }), { key: "ArrowDown" });
}

// Mounted at its real route so the test also pins where the tab lives.
function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/settings/engine"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/settings/engine" element={<EngineSettings />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("EngineSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("/settings/engine renders the internal-engine and embedding cards", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
    renderPage();
    expect(await screen.findByText("Internal engine")).toBeInTheDocument();
    expect(screen.getByText("Embedding")).toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "set a connection as the internal engine default",
    async () => {
      apiMock.list.mockResolvedValue({
        providers: [
          makeProvider({ name: "a", internal_default: false }),
          makeProvider({ name: "b", internal_default: false }),
        ],
      });
      apiMock.setInternalDefault.mockResolvedValue(
        makeProvider({ name: "b", internal_default: true }),
      );

      renderPage();
      await screen.findByText("Internal engine");

      // the internal-engine section's connection dropdown sets "b" as the default
      openSelect(/^model provider$/i);
      fireEvent.click(screen.getByRole("option", { name: "b" }));
      await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith("b"));
    },
  );

  acceptance(
    "provider-switching",
    "setting a new internal default clears the previous one",
    async () => {
      // A is the internal default; the dropdown reflects A as selected and lets
      // the operator switch to B, which the backend makes exclusive.
      apiMock.list.mockResolvedValue({
        providers: [
          makeProvider({ name: "A", internal_default: true }),
          makeProvider({ name: "B", internal_default: false }),
        ],
      });
      apiMock.setInternalDefault.mockResolvedValue(
        makeProvider({ name: "B", internal_default: true }),
      );

      renderPage();
      // The connection dropdown shows A as the current internal default.
      expect(await screen.findByRole("combobox", { name: /^model provider$/i })).toHaveTextContent("A");
      // Selecting B clears A on the backend (single-internal-default invariant).
      openSelect(/^model provider$/i);
      fireEvent.click(screen.getByRole("option", { name: "B" }));
      await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith("B"));
    },
  );
});
