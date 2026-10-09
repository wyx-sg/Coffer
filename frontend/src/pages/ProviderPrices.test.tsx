// src/pages/ProviderPrices.test.tsx — prices and context windows with their source (spec provider-switching).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { ModelPrice, Provider, ProviderModel } from "@/lib/api/providers";
import { ModelProvidersPage } from "./ModelProvidersPage";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/providers", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/providers")>()),
  providersApi: {
    list: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    prices: vi.fn(),
    windows: vi.fn(),
  },
}));
vi.mock("@/lib/api/proxy", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/proxy")>()),
  proxyApi: { status: vi.fn().mockResolvedValue({ port: 38471 }) },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: { pendingApprovals: vi.fn(), secretBoundary: vi.fn(), rejectApproval: vi.fn() },
}));
const { endpoint } = vi.hoisted(() => ({ endpoint: { models: [] as ProviderModel[] } }));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));
vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: { model: null, transcribe_model: null } }),
}));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useEndpointModels: () => ({
    data: { models: endpoint.models, message: "", reachable: true },
    error: null,
    isPending: false,
    isFetching: false,
    dataUpdatedAt: 1,
    refetch: vi.fn(),
  }),
  useListProviderModels: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const { providersApi } = await import("@/lib/api/providers");
const { scopeApi } = await import("@/lib/api/scope");
const { secretsApi } = await import("@/lib/api/secret");
const api = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const provider = (uid: string, over: Partial<Provider> = {}): Provider => ({
  uid,
  name: uid,
  protocol: "openai",
  base_url: "https://openrouter.ai/api/v1",
  anthropic_base_url: null,
  secret_ref: `provider/${uid}`,
  local_runtime: null,
  compatible_agents: ["codex"],
  served_agents: ["codex"],
  transcribe_default: false,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...over,
});
const chat = (...ids: string[]): ProviderModel[] => ids.map((id) => ({ id, modality: "text" }));
const price = (model: string, over: Partial<ModelPrice>): ModelPrice => ({
  model,
  source: null,
  source_name: null,
  input: null,
  output: null,
  cache_read: null,
  cache_write_5m: null,
  cache_write_1h: null,
  tiered: false,
  source_updated: null,
  ...over,
});

function serve(list: Provider[]) {
  api.list.mockResolvedValue({ providers: list });
  api.get.mockImplementation(async (uid: string) => list.find((p) => p.uid === uid));
  api.update.mockImplementation(async (uid: string) => list.find((p) => p.uid === uid));
}

function renderAt(uid: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[`/model-providers/${uid}`]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/model-providers/:uid" element={<ModelProvidersPage />} />
          <Route path="*" element={null} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const rowOf = (id: string) =>
  screen.getByRole("switch", { name: `Offered: ${id}` }).closest("tr") as HTMLElement;

describe("prices", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    endpoint.models = chat("mine", "reported", "listed", "unknown");
    (scopeApi.get as ReturnType<typeof vi.fn>).mockResolvedValue({ scope: null });
    (secretsApi.pendingApprovals as ReturnType<typeof vi.fn>).mockResolvedValue({
      approvals: [],
    });
    api.windows.mockResolvedValue({ windows: [] });
    api.prices.mockResolvedValue({
      bundled_version: "genai-prices@x",
      prices: [
        price("mine", { source: "user", input: 1.5, output: 12 }),
        price("reported", { source: "provider", source_name: "OpenRouter", input: 3, output: 15 }),
        price("listed", {
          source: "bundled",
          source_name: "OpenAI",
          input: 1.25,
          output: 10,
          source_updated: "2026-09-30",
        }),
        price("unknown", {}),
      ],
    });
  });

  acceptance("provider-switching", "each price names where it came from", async () => {
    serve([provider("router")]);
    renderAt("router");
    await waitFor(() => expect(within(rowOf("mine")).getByText("You set")).toBeInTheDocument());
    expect(within(rowOf("mine")).getByText("$1.50 · $12.00 / 1M")).toBeInTheDocument();
    // The Models line says once where prices usually come from (here the provider's
    // own API); a row is marked only when it differs.
    expect(
      screen.getByText(/^Prices per 1M tokens \(input · output\) from OpenRouter/),
    ).toBeInTheDocument();
    expect(within(rowOf("reported")).queryByText(/^From /)).toBeNull();
    expect(within(rowOf("listed")).getByText("Bundled")).toBeInTheDocument();
    expect(within(rowOf("unknown")).getByLabelText("No price known for unknown")).toHaveTextContent(
      "—",
    );
    expect(api.prices).toHaveBeenCalledWith("router", ["mine", "reported", "listed", "unknown"]);
  });

  test("setting a price on an unrestricted provider keeps every model offered", async () => {
    serve([provider("router")]);
    renderAt("router");
    fireEvent.click(await within(await waitFor(() => rowOf("unknown"))).findByText("Set price…"));
    const dialog = await screen.findByRole("dialog");
    const [input, output] = within(dialog).getAllByRole("textbox");
    fireEvent.change(input, { target: { value: "0.5" } });
    fireEvent.change(output, { target: { value: "2" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.update).toHaveBeenCalled());
    const models = api.update.mock.calls[0][1].models as ProviderModel[];
    expect(models.map((m) => m.id)).toEqual(["mine", "reported", "listed", "unknown"]);
    expect(models.find((m) => m.id === "unknown")?.price).toEqual({ input: 0.5, output: 2 });
  });

  test("Reset removes the price you set", async () => {
    serve([
      provider("router", {
        models: [{ id: "mine", modality: "text", price: { input: 1.5, output: 12 } }],
      }),
    ]);
    renderAt("router");
    // No Reset link in the cell: the price opens its dialog, which holds Reset to default.
    const row = await waitFor(() => rowOf("mine"));
    expect(within(row).queryByText("Reset")).toBeNull();
    fireEvent.click(await within(row).findByRole("button", { name: /change the price/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Reset to default" }));
    await waitFor(() => expect(api.update).toHaveBeenCalled());
    expect(api.update.mock.calls[0][1].models[0]).toMatchObject({ id: "mine", price: null });
  });

  test("a local runtime shows no cost", async () => {
    serve([
      provider("ollama", {
        base_url: "http://127.0.0.1:11434/v1",
        secret_ref: null,
        local_runtime: { runtime: "ollama", version: "0.14.2", wires: ["openai"] },
      }),
    ]);
    api.prices.mockResolvedValue({
      bundled_version: "x",
      prices: endpoint.models.map((m) => price(m.id, { source: "local", input: 0, output: 0 })),
    });
    renderAt("ollama");
    expect(await screen.findAllByText("Local · no cost")).not.toHaveLength(0);
  });
});

describe("context windows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    endpoint.models = [
      { id: "mine", modality: "text" },
      { id: "reported", modality: "text", context_window: 200_000 },
      { id: "listed", modality: "text" },
      { id: "unknown", modality: "text" },
    ];
    (scopeApi.get as ReturnType<typeof vi.fn>).mockResolvedValue({ scope: null });
    (secretsApi.pendingApprovals as ReturnType<typeof vi.fn>).mockResolvedValue({
      approvals: [],
    });
    api.prices.mockResolvedValue({ bundled_version: "x", prices: [] });
    api.windows.mockResolvedValue({
      windows: [
        { model: "mine", tokens: 64_000, source: "user" },
        { model: "reported", tokens: 200_000, source: "endpoint" },
        { model: "listed", tokens: 1_000_000, source: "bundled" },
        { model: "unknown", tokens: null, source: null },
      ],
    });
  });

  acceptance(
    "provider-switching",
    "each model's window names where it came from and can be set",
    async () => {
      serve([provider("router")]);
      renderAt("router");
      await waitFor(() => expect(within(rowOf("mine")).getByText("64K")).toBeInTheDocument());
      expect(within(rowOf("mine")).getByText("You set")).toBeInTheDocument();
      expect(within(rowOf("reported")).getByText("From the endpoint")).toBeInTheDocument();
      expect(within(rowOf("listed")).getByText("1M")).toBeInTheDocument();
      expect(within(rowOf("listed")).getByText("Bundled")).toBeInTheDocument();
      expect(
        within(rowOf("unknown")).getByLabelText("No context window known for unknown"),
      ).toHaveTextContent("—");

      fireEvent.click(within(rowOf("unknown")).getByText("Set window…"));
      const dialog = await screen.findByRole("dialog");
      fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "128k" } });
      fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
      await waitFor(() => expect(api.update).toHaveBeenCalled());
      const models = api.update.mock.calls[0][1].models as ProviderModel[];
      // An unrestricted provider is written out whole, each row keeping the window
      // its endpoint reported.
      expect(models.map((m) => m.id)).toEqual(["mine", "reported", "listed", "unknown"]);
      expect(models.find((m) => m.id === "reported")?.context_window).toBe(200_000);
      expect(models.find((m) => m.id === "unknown")?.user_context_window).toBe(128_000);
    },
  );

  test("Reset removes the window you set", async () => {
    serve([
      provider("router", {
        models: [{ id: "mine", modality: "text", user_context_window: 64_000 }],
      }),
    ]);
    renderAt("router");
    const row = await waitFor(() => rowOf("mine"));
    fireEvent.click(await within(row).findByRole("button", { name: /change the context window/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Reset to default" }));
    await waitFor(() => expect(api.update).toHaveBeenCalled());
    expect(api.update.mock.calls[0][1].models[0]).toMatchObject({
      id: "mine",
      user_context_window: null,
    });
  });

  test("a window that is not a sane token count cannot be saved", async () => {
    serve([provider("router")]);
    renderAt("router");
    fireEvent.click(await within(await waitFor(() => rowOf("unknown"))).findByText("Set window…"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "12" } });
    expect(within(dialog).getByText(/between 1k and 100m/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
  });
});
