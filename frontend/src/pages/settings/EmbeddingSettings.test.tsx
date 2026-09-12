// frontend/src/pages/settings/EmbeddingSettings.test.tsx
//
// The global embedding card asks the same two questions the internal-engine card
// above it asks: WHICH model provider, then WHICH of its models (knowledge
// FR-077). There is no add-a-model form and no key field: both belong to the
// connection. What is pinned here is that shape, the re-embed confirmation, and
// that the daemon's 422 lands inline on the card rather than in a toast.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, Navigate, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import type { Provider, ProviderModel } from "@/lib/api/providers";
import { EmbeddingSettings } from "./EmbeddingSettings";

vi.mock("@/lib/hooks/useEmbeddingConfig", () => ({
  useEmbeddingConfig: vi.fn(),
  useUpdateEmbeddingConfig: vi.fn(),
  useEmbeddingModels: vi.fn(),
}));
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useTestEmbedding: vi.fn() }));

const hooks = await import("@/lib/hooks/useEmbeddingConfig");
const { useProviders } = await import("@/lib/hooks/useProviders");
const { useTestEmbedding } = await import("@/lib/hooks/useModelIntrospection");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const mutate = vi.fn();
const testMutate = vi.fn();

afterEach(() => vi.clearAllMocks());

const provider = (name: string, models: ProviderModel[] = []): Provider => ({
  name,
  protocol: "openai",
  base_url: "https://gw/openai",
  credential_ref: `provider/${name}/key`,
  compatible_agents: ["codex"],
  is_active: false,
  internal_default: false,
  models,
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

interface SeedOptions {
  config?: Partial<{
    enabled: boolean;
    connection: string | null;
    model: string | null;
    dimensions: number;
  }>;
  providers?: Provider[];
  /** What the chosen connection offers as embedding models. */
  options?: string[];
  updateError?: unknown;
}

function seed({
  config = {},
  providers = [provider("acme")],
  options = [],
  updateError,
}: SeedOptions = {}) {
  vi.mocked(hooks.useEmbeddingConfig).mockReturnValue({
    data: {
      enabled: false,
      connection: null,
      model: null,
      dimensions: 768,
      default_chunk_size: 512,
      default_chunk_overlap: 64,
      updated_at: null,
      ...config,
    },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useEmbeddingConfig>);
  vi.mocked(hooks.useUpdateEmbeddingConfig).mockReturnValue({
    mutate,
    isPending: false,
    error: updateError ?? null,
  } as unknown as ReturnType<typeof hooks.useUpdateEmbeddingConfig>);
  vi.mocked(hooks.useEmbeddingModels).mockReturnValue({ options, probing: false });
  vi.mocked(useProviders).mockReturnValue({ data: providers } as unknown as ReturnType<
    typeof useProviders
  >);
  vi.mocked(useTestEmbedding).mockReturnValue({
    mutate: testMutate,
    reset: vi.fn(),
    isPending: false,
    data: undefined,
  } as unknown as ReturnType<typeof useTestEmbedding>);
}

// Radix Select: open via keyboard (jsdom has no pointer layout), then click the
// rendered option.
function pick(triggerName: RegExp, option: string) {
  fireEvent.keyDown(screen.getByRole("combobox", { name: triggerName }), { key: "ArrowDown" });
  fireEvent.click(screen.getByRole("option", { name: option }));
}

describe("EmbeddingSettings", () => {
  test("is two pickers — a provider and one of its models — with no add-model form", () => {
    seed();
    render(<EmbeddingSettings />, { wrapper: wrap });

    expect(screen.getByRole("combobox", { name: /embedding provider/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /embedding model/i })).toBeInTheDocument();
    // The add/edit dialog and everything it asked for (a provider name, a base
    // URL, an API key) are gone: the connection owns all three.
    expect(screen.queryByRole("button", { name: /add model/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/base url/i)).not.toBeInTheDocument();
    // Unconfigured: retrieval falls back to keyword/grep, and it says so.
    expect(screen.getByText(/falls back to keyword\/grep/i)).toBeInTheDocument();
  });

  test("picking a provider then one of its models saves the pair", () => {
    seed({ providers: [provider("acme"), provider("local")], options: ["bge-m3"] });
    render(<EmbeddingSettings />, { wrapper: wrap });

    pick(/embedding provider/i, "local");
    // Choosing a provider alone writes nothing — a config with a connection and
    // no model is one the daemon refuses.
    expect(mutate).not.toHaveBeenCalled();

    pick(/embedding model/i, "bge-m3");
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ connection: "local", model: "bge-m3" }),
    );
  });

  test("only the connection's embedding models are offered", () => {
    // The narrowing itself lives in useEmbeddingModels; what the card must do is
    // offer exactly what that hook returns for the chosen connection.
    seed({
      config: { connection: "acme" },
      providers: [
        provider("acme", [
          { id: "gpt-4o", modality: "text" },
          { id: "text-embedding-3-large", modality: "embedding" },
        ]),
      ],
      options: ["text-embedding-3-large"],
    });
    render(<EmbeddingSettings />, { wrapper: wrap });

    fireEvent.keyDown(screen.getByRole("combobox", { name: /embedding model/i }), {
      key: "ArrowDown",
    });
    expect(screen.getByRole("option", { name: "text-embedding-3-large" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "gpt-4o" })).not.toBeInTheDocument();
  });

  test("a provider curating no embedding model says so and offers nothing to pick", () => {
    seed({
      config: { connection: "acme" },
      providers: [provider("acme", [{ id: "gpt-4o", modality: "text" }])],
      options: [],
    });
    render(<EmbeddingSettings />, { wrapper: wrap });

    expect(screen.getByText(/offers no embedding model/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /embedding model/i })).toBeDisabled();
  });

  test("changing an already-configured model asks before re-embedding", async () => {
    seed({
      config: { enabled: true, connection: "acme", model: "bge-m3", dimensions: 1024 },
      options: ["bge-m3", "text-embedding-3-small"],
    });
    render(<EmbeddingSettings />, { wrapper: wrap });

    pick(/embedding model/i, "text-embedding-3-small");
    // Held behind the confirmation, not persisted yet.
    expect(mutate).not.toHaveBeenCalled();
    expect(await screen.findByText(/change embedding model\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /change & re-embed/i }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({ connection: "acme", model: "text-embedding-3-small" }),
      ),
    );
  });

  test("changing only the dimensions also asks for confirmation", async () => {
    seed({
      config: { enabled: true, connection: "acme", model: "bge-m3", dimensions: 1024 },
      options: ["bge-m3"],
    });
    render(<EmbeddingSettings />, { wrapper: wrap });

    const dims = screen.getByLabelText(/dimensions/i);
    fireEvent.change(dims, { target: { value: "512" } });
    fireEvent.blur(dims);

    expect(mutate).not.toHaveBeenCalled();
    expect(await screen.findByText(/change embedding model\?/i)).toBeInTheDocument();
  });

  test("auto-saves (no inline Save button) — toggling enable PUTs the config", () => {
    seed({ config: { enabled: true, connection: "acme", model: "bge-m3", dimensions: 1024 } });
    render(<EmbeddingSettings />, { wrapper: wrap });

    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch"));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false, connection: "acme", model: "bge-m3" }),
    );
  });

  test("a refused selection is shown on the card, verbatim, not as a toast", () => {
    // The daemon's 422 names WHICH rule was broken; the generic
    // `errors.CONFIG_INVALID` string would throw that half away.
    seed({
      config: { connection: "anth", model: "bge-m3" },
      providers: [provider("anth")],
      updateError: new ApiError(
        "CONFIG_INVALID",
        "connection 'anth' speaks anthropic, which serves no embedding API; pick an openai-compatible or ollama connection",
      ),
    });
    render(<EmbeddingSettings />, { wrapper: wrap });

    expect(screen.getByRole("alert")).toHaveTextContent(/serves no embedding API/i);
  });

  test("testing the model probes the connection, not a restated endpoint", () => {
    seed({ config: { connection: "acme", model: "bge-m3" }, options: ["bge-m3"] });
    render(<EmbeddingSettings />, { wrapper: wrap });

    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));
    expect(testMutate).toHaveBeenCalledWith({ connection: "acme", model: "bge-m3" });
  });
});

describe("legacy /settings/embedding redirect", () => {
  test("redirects the old embedding route to the Engine tab", async () => {
    // Embedding config has no page of its own — it is one of the two cards on
    // Settings → Engine, alongside the internal-engine selection. This mirrors
    // the redirect declared in router.tsx.
    const router = createMemoryRouter(
      [
        { path: "/settings/engine", element: <div>engine settings</div> },
        {
          path: "/settings/embedding",
          element: <Navigate to="/settings/engine" replace />,
        },
      ],
      { initialEntries: ["/settings/embedding"] },
    );
    render(<RouterProvider router={router} />);
    await waitFor(() => expect(screen.getByText("engine settings")).toBeInTheDocument());
    expect(router.state.location.pathname).toBe("/settings/engine");
  });
});
