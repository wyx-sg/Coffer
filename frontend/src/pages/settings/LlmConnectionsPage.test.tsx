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
  internal_default: false,
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
        <LlmConnectionsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("LlmConnectionsPage", () => {
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

  acceptance(
    "011-provider-switching",
    "create an ollama connection without a credential",
    async () => {
      apiMock.list.mockResolvedValue({ providers: [] });
      apiMock.create.mockResolvedValue(
        makeProvider({
          name: "local-llm",
          wire_format: "ollama",
          credential_ref: null,
          internal_default: false,
        }),
      );

      renderPage();
      // open the add dialog
      fireEvent.click(await screen.findByRole("button", { name: /Add connection/i }));

      // choose the ollama wire — the credential field disappears
      fireEvent.change(screen.getByLabelText("Wire format"), { target: { value: "ollama" } });
      expect(screen.queryByLabelText("API key")).not.toBeInTheDocument();

      fireEvent.change(screen.getByLabelText("Name"), { target: { value: "local-llm" } });
      fireEvent.change(screen.getByLabelText("Base URL"), {
        target: { value: "http://localhost:11434" },
      });
      fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "llama3" } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => expect(apiMock.create).toHaveBeenCalledTimes(1));
      const body = apiMock.create.mock.calls[0][0];
      expect(body).toMatchObject({
        name: "local-llm",
        wire_format: "ollama",
        base_url: "http://localhost:11434",
        model: "llama3",
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

      // the star toggle for "b" sets it as the internal-engine default
      fireEvent.click(screen.getByRole("button", { name: /use "b" for/i }));
      await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith("b"));
    },
  );

  acceptance(
    "011-provider-switching",
    "setting a new internal default clears the previous one",
    async () => {
      // A is the internal default; the UI must not offer to re-set A (its toggle
      // is disabled) and must allow setting B, which the backend makes exclusive.
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
      await screen.findByText("A");

      // A already the internal default → its toggle is disabled (no re-set).
      const aToggle = screen.getByRole("button", { name: /use "A" for/i });
      expect(aToggle).toBeDisabled();
      // Setting B clears A on the backend (single-internal-default invariant).
      fireEvent.click(screen.getByRole("button", { name: /use "B" for/i }));
      await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith("B"));
    },
  );

  test("edits a connection via the card pencil action (name + wire locked)", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider({ name: "acme" })] });
    apiMock.update.mockResolvedValue(makeProvider({ name: "acme", model: "claude-sonnet-4-6" }));

    renderPage();
    await screen.findByText("acme");

    // open the edit dialog from the card
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    // name + wire are fixed (resource id / projection target)
    expect((screen.getByLabelText("Name") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Wire format") as HTMLSelectElement).disabled).toBe(true);
    // the secret is optional in edit mode (no value re-entry required)
    expect((screen.getByLabelText("API key") as HTMLInputElement).required).toBe(false);

    // change the model and save → PATCH only the editable fields
    fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "claude-sonnet-4-6" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({ model: "claude-sonnet-4-6" }),
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
