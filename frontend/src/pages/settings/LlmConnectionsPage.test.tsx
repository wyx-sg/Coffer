// pages/settings/LlmConnectionsPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { acceptance } from "@/test/acceptance";
import { LlmConnectionsPage } from "./LlmConnectionsPage";
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

// The Embedding card makes its own network calls; stub it — this page test
// covers the connection library + internal-engine selection only.
vi.mock("./EmbeddingSettings", () => ({
  EmbeddingSettings: () => <div data-testid="embedding-settings" />,
}));

// The dialog's introspection (detect / test / fetch) hits the network; stub the
// hooks. `detect` synchronously resolves to a protocol so the create flow works.
let detectResult = "openai";
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useDetectProtocol: () => ({
    isPending: false,
    mutate: (_p: unknown, o?: { onSuccess?: (r: { protocol: string }) => void }) =>
      o?.onSuccess?.({ protocol: detectResult }),
  }),
  useListProviderModels: () => ({ isPending: false, mutate: vi.fn(), data: undefined }),
  useTestConnection: () => ({ isPending: false, mutate: vi.fn(), data: undefined }),
  useTestEmbedding: () => ({ isPending: false, mutate: vi.fn(), data: undefined }),
}));

// The internal-engine section reads/writes its own singleton config (network);
// stub the hooks — this page test asserts the connection-selection wiring only.
vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: { model: null, updated_at: null } }),
  useSetInternalEngineModel: () => ({ isPending: false, mutate: vi.fn() }),
}));

const { providersApi } = await import("@/lib/api/providers");
const apiMock = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const makeProvider = (overrides?: Partial<Provider>): Provider => ({
  name: "acme",
  protocol: "anthropic",
  base_url: "https://gw/anthropic",
  credential_ref: "provider/acme/key",
  is_active: false,
  internal_default: false,
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

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <LlmConnectionsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("LlmConnectionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    detectResult = "openai";
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
        protocol: "anthropic",
        projected: ["cc"],
        skipped: [],
      });

      renderPage();

      // lists the connections
      expect(await screen.findByText("official")).toBeInTheDocument();
      expect(screen.getByText("kimi")).toBeInTheDocument();

      // the active one is marked and cannot be re-switched; the inactive one can
      const switchButtons = screen.getAllByRole("button", { name: "Switch" });
      expect(switchButtons).toHaveLength(1); // only "kimi" (official is active)
      fireEvent.click(switchButtons[0]);

      await waitFor(() => expect(apiMock.activate).toHaveBeenCalledWith("kimi"));
    },
  );

  test("create falls back to a manual type pick when detection is inconclusive", async () => {
    detectResult = "unknown";
    apiMock.list.mockResolvedValue({ providers: [] });
    apiMock.create.mockResolvedValue(makeProvider({ name: "myconn", protocol: "openai" }));

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Add connection/i }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "myconn" } });
    fireEvent.change(screen.getByLabelText("Base URL"), { target: { value: "https://gw/v1" } });
    const key = screen.getByLabelText("API key");
    fireEvent.change(key, { target: { value: "sk-x" } });
    fireEvent.blur(key); // detection runs → "unknown" → manual select appears

    const sel = screen.getByLabelText("Connection type");
    fireEvent.change(sel, { target: { value: "openai" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiMock.create).toHaveBeenCalledTimes(1));
    expect(apiMock.create.mock.calls[0][0]).toMatchObject({
      name: "myconn",
      protocol: "openai",
      secret_value: "sk-x",
    });
  });

  acceptance(
    "011-provider-switching",
    "create an ollama connection without a credential",
    async () => {
      apiMock.list.mockResolvedValue({ providers: [] });
      apiMock.create.mockResolvedValue(
        makeProvider({
          name: "local-llm",
          protocol: "ollama",
          credential_ref: null,
          internal_default: false,
        }),
      );

      detectResult = "ollama";
      renderPage();
      // open the add dialog
      fireEvent.click(await screen.findByRole("button", { name: /Add connection/i }));

      fireEvent.change(screen.getByLabelText("Name"), { target: { value: "local-llm" } });
      // entering the base URL auto-detects the wire (→ ollama); blur triggers it
      const base = screen.getByLabelText("Base URL");
      fireEvent.change(base, { target: { value: "http://localhost:11434" } });
      fireEvent.blur(base);
      // ollama needs no key — the credential field disappears once detected
      expect(screen.queryByLabelText("API key")).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => expect(apiMock.create).toHaveBeenCalledTimes(1));
      const body = apiMock.create.mock.calls[0][0];
      expect(body).toMatchObject({
        name: "local-llm",
        protocol: "ollama",
        base_url: "http://localhost:11434",
      });
      // NEITHER secret_value nor credential_ref is sent for ollama.
      expect(body.secret_value).toBeUndefined();
      expect(body.credential_ref).toBeUndefined();
    },
  );

  acceptance(
    "011-provider-switching",
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
      await screen.findByText("b");

      // the internal-engine section's connection dropdown sets "b" as the default
      openSelect(/connection/i);
      fireEvent.click(screen.getByRole("option", { name: "b" }));
      await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith("b"));
    },
  );

  acceptance(
    "011-provider-switching",
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
      expect(await screen.findByRole("combobox", { name: /connection/i })).toHaveTextContent("A");
      // Selecting B clears A on the backend (single-internal-default invariant).
      openSelect(/connection/i);
      fireEvent.click(screen.getByRole("option", { name: "B" }));
      await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith("B"));
    },
  );

  test("edits a connection via the card pencil action (name + protocol locked)", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider({ name: "acme" })] });
    apiMock.update.mockResolvedValue(makeProvider({ name: "acme", base_url: "https://gw/v2" }));

    renderPage();
    await screen.findByText("acme");

    // open the edit dialog from the card
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    // name is fixed (resource id); the protocol is shown read-only (no detect/edit)
    expect((screen.getByLabelText("Name") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Detect type" })).not.toBeInTheDocument();
    // the secret is optional in edit mode (no value re-entry required)
    expect((screen.getByLabelText("API key") as HTMLInputElement).required).toBe(false);
    // no model field on the connection dialog — the model lives on the agent (E3)
    expect(screen.queryByLabelText("Model ID")).not.toBeInTheDocument();

    // change the base URL and save → PATCH only the editable fields
    fireEvent.change(screen.getByLabelText("Base URL"), { target: { value: "https://gw/v2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({ base_url: "https://gw/v2" }),
    );
    // no fresh secret typed → secret_value omitted
    expect(apiMock.update.mock.calls[0][1].secret_value).toBeUndefined();
  });

  test("renders the embedding card at the bottom", async () => {
    apiMock.list.mockResolvedValue({ providers: [] });
    renderPage();
    expect(await screen.findByTestId("embedding-settings")).toBeInTheDocument();
  });
});
