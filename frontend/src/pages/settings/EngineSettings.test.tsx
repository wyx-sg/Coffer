// frontend/src/pages/settings/EngineSettings.test.tsx
//
// The Coffer's model section of Settings › General holds Coffer's own engine
// configs: the engine picker (connection + model) with the bound on ONE call
// under it, the speech-to-text picker on its own connection, each with a Test
// and a state line, and the unattended passes below. Internal configuration
// is not a resource, so none of it sits on the Model providers page.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
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
const setEngineModel = vi.fn();
const setSttModel = vi.fn();
// The Test button's probe. Each test says what the endpoint answers.
const testMutate = vi.fn();
// The speech-to-text Test asks the endpoint for its model list instead.
const listMutate = vi.fn();

// The engine config is a singleton the whole page reads; each test sets the one
// it needs before rendering. Nested behind arrows so the mock factory, which
// runs at import time, never touches it before the declaration below.
let engineConfig: Partial<InternalEngineConfig> = {};

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: engineConfig }),
  useSetInternalEngineModel: () => ({ isPending: false, mutate: setEngineModel }),
  useSetModelTimeout: () => ({ isPending: false, mutate: setBound }),
  // The speech-to-text picker sits in this section too; its own suite covers it.
  useSetTranscribeModel: () => ({ isPending: false, mutate: setSttModel }),
}));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ isPending: false, mutate: listMutate, data: undefined }),
  useTestConnection: () => ({ isPending: false, mutate: testMutate }),
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
    secret_ref: "provider/acme/key",
    local_runtime: null,
    compatible_agents: ["claude_code"],
    is_active: false,
    title: null,
    internal_default: false,
    transcribe_default: false,
    fallback: true,
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

/** The pickers render once the connection list has arrived. */
const ready = () => screen.findByRole("combobox", { name: /^model provider$/i });

// Mounted at its real route so the test also pins where the tab lives.
function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/settings/engine"]}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <Routes>
            <Route path="/settings/engine" element={<EngineSettings />} />
          </Routes>
        </TooltipProvider>
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

  acceptance(
    "internal-engine",
    "Settings → Coffer's model shows and changes both halves",
    async () => {
      apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
      renderPage();
      await ready();
      expect(screen.getByText("Coffer's model")).toBeInTheDocument();
      // The embedding card went with vector retrieval: there is no index left
      // for an embedding model to feed (ADR knowledge-is-plain-files).
      expect(screen.queryByText("Embedding")).not.toBeInTheDocument();
      // The passes Coffer runs on its own are switched on the pages they
      // upkeep (Knowledge and Memory), not here.
      expect(screen.queryByText("Automatic upkeep")).not.toBeInTheDocument();
      // Speech gets its own card: it runs on a second connection flag, and
      // nothing falls back from it to the engine's.
      expect(screen.getByText("Speech to text")).toBeInTheDocument();
    },
  );

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

  acceptance(
    "internal-engine",
    "bound how long one call to Coffer's own model may take",
    async () => {
      engineConfig = { ...engineConfig, model_timeout_s: 300 };
      apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
      renderPage();

      expect(await screen.findByText("5 min")).toBeInTheDocument();
    },
  );

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

  acceptance(
    "internal-engine",
    "bound how long one call to Coffer's own model may take",
    async () => {
      apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
      renderPage();
      await ready();

      openSelect(/^time limit per call$/i);
      fireEvent.click(screen.getByRole("option", { name: "5 min" }));

      await waitFor(() => expect(setBound).toHaveBeenCalledWith(300));
    },
  );

  acceptance(
    "internal-engine",
    "bound how long one call to Coffer's own model may take",
    async () => {
      engineConfig = { ...engineConfig, model_timeout_s: 300 };
      apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
      renderPage();
      await ready();

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
    await ready();

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

  // Scenario (revise-web-ui-ia): "coffer's model is chosen in settings general"
  test("the engine picker lists only the chosen provider's models and saves on selection", async () => {
    apiMock.list.mockResolvedValue({
      providers: [
        makeProvider({
          name: "A",
          internal_default: true,
          models: [
            { id: "a-chat", modality: "text" },
            { id: "a-whisper", modality: "audio" },
          ],
        }),
        makeProvider({ name: "B", models: [{ id: "b-chat", modality: "text" }] }),
      ],
    });
    renderPage();
    await ready();

    openSelect(/^model$/i);
    expect(screen.getByRole("option", { name: "a-chat" })).toBeInTheDocument();
    // Not the other provider's, and not A's speech model.
    expect(screen.queryByRole("option", { name: "b-chat" })).toBeNull();
    expect(screen.queryByRole("option", { name: "a-whisper" })).toBeNull();
    fireEvent.click(screen.getByRole("option", { name: "a-chat" }));

    await waitFor(() => expect(setEngineModel).toHaveBeenCalledWith("a-chat"));
    expect(screen.queryByRole("button", { name: /^save$/i })).toBeNull();
  });

  // Scenario (revise-web-ui-ia): "an unset picker says what coffer does without it"
  test("an unset picker reads as not set and says what Coffer does without it", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
    renderPage();
    await ready();

    const [engine, stt] = screen.getAllByTestId("model-state");
    expect(engine).toHaveTextContent(/not set/i);
    expect(engine).toHaveTextContent(/no internal pass runs/i);
    expect(stt).toHaveTextContent(/not set/i);
    expect(stt).toHaveTextContent(/reach the agent as audio files/i);
    // Nothing to test while either half is missing.
    for (const b of screen.getAllByRole("button", { name: /^test /i })) expect(b).toBeDisabled();
  });

  // Scenario (revise-web-ui-ia): "testing a picker shows a failing pair inline"
  test("a failing test on the engine reads as failing with the endpoint's error", async () => {
    engineConfig = { ...engineConfig, model: "llama3.1:8b" };
    apiMock.list.mockResolvedValue({
      providers: [makeProvider({ name: "A", internal_default: true })],
    });
    testMutate.mockImplementation((_probe, opts) =>
      opts.onSuccess({ ok: false, message: "invalid api key" }),
    );
    renderPage();
    await ready();
    expect(screen.getAllByTestId("model-state")[0]).toHaveTextContent(/^set$/i);

    fireEvent.click(screen.getByRole("button", { name: /test coffer's engine/i }));

    expect(testMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: "anthropic",
        base_url: "https://gw/anthropic",
        secret_ref: "provider/acme/key",
        model: "llama3.1:8b",
      }),
      expect.anything(),
    );
    const state = screen.getAllByTestId("model-state")[0];
    expect(state).toHaveTextContent(/failing/i);
    expect(state).toHaveTextContent(/invalid api key/i);
    expect(state).toHaveTextContent(/distil and curation wait/i);
    // The pair is kept as it was.
    expect(setEngineModel).not.toHaveBeenCalled();
    expect(apiMock.setInternalDefault).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: /^model$/i })).toHaveTextContent("llama3.1:8b");
  });

  test("a passing test reads as answering", async () => {
    engineConfig = { ...engineConfig, model: "llama3.1:8b" };
    apiMock.list.mockResolvedValue({
      providers: [makeProvider({ name: "A", internal_default: true })],
    });
    testMutate.mockImplementation((_probe, opts) =>
      opts.onSuccess({ ok: true, message: "connection ok" }),
    );
    renderPage();
    await ready();

    fireEvent.click(screen.getByRole("button", { name: /test coffer's engine/i }));

    expect(screen.getAllByTestId("model-state")[0]).toHaveTextContent(/answering/i);
  });

  // Scenario (revise-web-ui-ia, internal-engine): "a failed test leaves coffer's model as it was"
  test("a failed speech-to-text test is shown inline and writes nothing", async () => {
    engineConfig = { ...engineConfig, transcribe_model: "whisper-1" };
    apiMock.list.mockResolvedValue({
      providers: [
        makeProvider({
          name: "B",
          transcribe_default: true,
          models: [{ id: "whisper-1", modality: "audio" }],
        }),
      ],
    });
    // Unreachable: the listing request itself fails.
    listMutate.mockImplementation((_probe, opts) =>
      opts?.onError?.(new Error("connection refused")),
    );
    renderPage();
    await ready();

    fireEvent.click(screen.getByRole("button", { name: /test speech to text/i }));

    const state = screen.getAllByTestId("model-state")[1];
    expect(state).toHaveTextContent(/failing/i);
    expect(state).toHaveTextContent(/connection refused/i);
    // A chat probe would fail on a speech model even on a healthy endpoint.
    expect(testMutate).not.toHaveBeenCalled();
    expect(setSttModel).not.toHaveBeenCalled();
    expect(apiMock.setTranscribeDefault).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: /^transcription model$/i })).toHaveTextContent(
      "whisper-1",
    );
  });

  // Scenario (revise-web-ui-ia, internal-engine): "the general tab's coffer's model section shows and changes both halves"
  test("the section shows the chosen pair and no upkeep, and each edit saves alone", async () => {
    engineConfig = { ...engineConfig, model: "a-chat" };
    apiMock.list.mockResolvedValue({
      providers: [
        makeProvider({
          name: "A",
          internal_default: true,
          models: [
            { id: "a-chat", modality: "text" },
            { id: "a-big", modality: "text" },
          ],
        }),
      ],
    });
    renderPage();

    await ready();
    const section = screen.getByTestId("coffer-model-section");
    expect(within(section).getByRole("combobox", { name: /^model provider$/i })).toHaveTextContent(
      "A",
    );
    expect(within(section).getByRole("combobox", { name: /^model$/i })).toHaveTextContent("a-chat");
    // No upkeep switch, interval or curation owner: those live on the
    // Knowledge and Memory pages. The one switch left is the price refresh.
    expect(screen.queryAllByRole("switch").filter((s) => s.id !== "price-refresh")).toHaveLength(0);
    expect(screen.queryByText(/curation runs on/i)).toBeNull();

    openSelect(/^model$/i);
    fireEvent.click(screen.getByRole("option", { name: "a-big" }));
    await waitFor(() => expect(setEngineModel).toHaveBeenCalledWith("a-big"));

    // Only the edited values were written — nothing else moved.
    expect(setBound).not.toHaveBeenCalled();
    expect(setSttModel).not.toHaveBeenCalled();
    expect(apiMock.setInternalDefault).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /^save$/i })).toBeNull();
  });
});
