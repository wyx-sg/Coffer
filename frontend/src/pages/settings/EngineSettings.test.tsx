// frontend/src/pages/settings/EngineSettings.test.tsx
//
// Settings → Coffer's model holds Coffer's own engine configs: the internal LLM
// connection + model, the bound on ONE call to that model, and — in its own
// card — the connection and model speech is transcribed with. It moved here off
// the model-provider page, which is now purely the connection library agents
// draw from — internal configuration is not a resource.
import { beforeEach, describe, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { acceptance } from "@/test/acceptance";
import { EngineSettings } from "./EngineSettings";
import type { InternalEngineConfig } from "@/lib/api/internalEngine";
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
      setTranscribeDefault: vi.fn(),
    },
  };
});

// The internal-engine section reads/writes its own singleton config, and the
// model dropdown lists the chosen endpoint's models — both hit the network.
const setBound = vi.fn();

// The engine config is a singleton the whole page reads; each test sets the one
// it needs before rendering. Nested behind arrows so the mock factory, which
// runs at import time, never touches it before the declaration below.
let engineConfig: Partial<InternalEngineConfig> = {};

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: engineConfig }),
  useSetInternalEngineModel: () => ({ isPending: false, mutate: vi.fn() }),
  useSetModelTimeout: () => ({ isPending: false, mutate: setBound }),
  // The speech-to-text card sits on this page too; its own suite covers it.
  useSetTranscribeModel: () => ({ isPending: false, mutate: vi.fn() }),
  // The upkeep card sits on this page too; its own suite covers its behaviour.
  useSetUpkeep: () => ({ isPending: false, mutate: vi.fn() }),
}));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ isPending: false, mutate: vi.fn(), data: undefined }),
}));

const { providersApi } = await import("@/lib/api/providers");
const apiMock = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

/** An opaque uid per fixture NAME. The connection dropdown carries the uid as
 *  each option's VALUE and the name as its LABEL, and the mutation takes the
 *  uid — so the two must be different strings, or an assertion on one of them
 *  would pass against the other. */
const UIDS: Record<string, string> = {
  acme: "cn-31f0",
  a: "cn-7ba2",
  b: "cn-c94d",
  A: "cn-1d6e",
  B: "cn-8402",
};
const uidFor = (name: string) => UIDS[name] ?? "cn-unlisted";

const makeProvider = (overrides?: Partial<Provider>): Provider => {
  const name = overrides?.name ?? "acme";
  return {
    uid: uidFor(name),
    name,
    protocol: "anthropic",
    base_url: "https://gw/anthropic",
    credential_ref: "provider/acme/key",
    compatible_agents: ["claude_code"],
    is_active: false,
    internal_default: false,
    transcribe_default: false,
    models: [],
    enabled: true,
    description: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
};

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
    engineConfig = {
      model: null,
      updated_at: null,
      upkeep: {},
      model_timeout_s: null,
      default_model_timeout_s: 60,
    };
  });

  acceptance("internal-engine", "Settings → Coffer's model shows and changes both halves", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
    renderPage();
    expect(await screen.findByText("Coffer's model")).toBeInTheDocument();
    // The embedding card went with vector retrieval: there is no index left
    // for an embedding model to feed (ADR knowledge-is-plain-files).
    expect(screen.queryByText("Embedding")).not.toBeInTheDocument();
    // The passes Coffer runs on its own belong beside the model they run on.
    expect(screen.getByText("Automatic upkeep")).toBeInTheDocument();
    // Speech gets its own card: it runs on a second connection flag, and
    // nothing falls back from it to the engine's.
    expect(screen.getByText("Speech to text")).toBeInTheDocument();
  });

  acceptance(
    "internal-engine",
    "bound how long one call to Coffer's own model may take",
    async () => {
      // A blank here would leave the reader unable to tell how long Coffer
      // actually waits before giving up on its own model.
      apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
      renderPage();

      expect(await screen.findByText("Default (1 min)")).toBeInTheDocument();
    },
  );

  acceptance("internal-engine", "bound how long one call to Coffer's own model may take", async () => {
    engineConfig = { ...engineConfig, model_timeout_s: 300 };
    apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
    renderPage();

    expect(await screen.findByText("5 min")).toBeInTheDocument();
  });

  acceptance(
    "internal-engine",
    "bound how long one call to Coffer's own model may take",
    async () => {
      // The CLI writes any number in range; showing only our own choices would
      // make a working setting read as one nobody made.
      engineConfig = { ...engineConfig, model_timeout_s: 45 };
      apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
      renderPage();

      expect(await screen.findByText("45s")).toBeInTheDocument();
    },
  );

  acceptance("internal-engine", "bound how long one call to Coffer's own model may take", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
    renderPage();
    await screen.findByText("Coffer's model");

    openSelect(/^time limit per call$/i);
    fireEvent.click(screen.getByRole("option", { name: "5 min" }));

    await waitFor(() => expect(setBound).toHaveBeenCalledWith(300));
  });

  acceptance(
    "internal-engine",
    "bound how long one call to Coffer's own model may take",
    async () => {
      engineConfig = { ...engineConfig, model_timeout_s: 300 };
      apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
      renderPage();
      await screen.findByText("Coffer's model");

      openSelect(/^time limit per call$/i);
      fireEvent.click(screen.getByRole("option", { name: "Default (1 min)" }));

      await waitFor(() => expect(setBound).toHaveBeenCalledWith(null));
    },
  );

  acceptance("provider-switching", "set a connection as the internal engine default", async () => {
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
    await screen.findByText("Coffer's model");

    // the internal-engine section's connection dropdown sets "b" as the default
    openSelect(/^model provider$/i);
    // Picked by the name on the option; sent as the uid behind it.
    fireEvent.click(screen.getByRole("option", { name: "b" }));
    await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith(uidFor("b")));
  });

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
      // The connection dropdown shows A as the current internal default — the
      // NAME, even though the value under it is A's uid.
      expect(await screen.findByRole("combobox", { name: /^model provider$/i })).toHaveTextContent(
        "A",
      );
      // Selecting B clears A on the backend (single-internal-default invariant).
      openSelect(/^model provider$/i);
      fireEvent.click(screen.getByRole("option", { name: "B" }));
      await waitFor(() => expect(apiMock.setInternalDefault).toHaveBeenCalledWith(uidFor("B")));
    },
  );
});
