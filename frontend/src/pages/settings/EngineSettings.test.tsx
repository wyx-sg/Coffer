// frontend/src/pages/settings/EngineSettings.test.tsx
//
// The Speech-to-text section of Settings › General: the speech-to-text picker
// (connection + model) with a Test and a state line, and the price-list switch. The unattended passes are switched
// on the Memory page, and none of this sits on the Model providers page.
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
      setTranscribeDefault: vi.fn(),
    },
  };
});

// The section reads/writes the settings singleton, and the model dropdown lists
// the chosen endpoint's models — both hit the network.
const setSttModel = vi.fn();
const testMutate = vi.fn();
// The speech-to-text Test asks the endpoint for its model list instead.
const listMutate = vi.fn();

// The engine config is a singleton the whole page reads; each test sets the one
// it needs before rendering. Nested behind arrows so the mock factory, which
// runs at import time, never touches it before the declaration below.
let engineConfig: Partial<InternalEngineConfig> = {};

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: engineConfig }),
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
    anthropic_base_url: null,
    secret_ref: "provider/acme/key",
    local_runtime: null,
    compatible_agents: ["claude_code"],
    served_agents: ["claude_code"],
    title: null,
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

/** The picker renders once the connection list has arrived. */
const ready = () => screen.findByRole("combobox", { name: /^transcription provider$/i });

// Mounted at its real route so the test also pins where the tab lives.
function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/settings/general"]}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <Routes>
            <Route path="/settings/general" element={<EngineSettings />} />
          </Routes>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("EngineSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    engineConfig = { updated_at: null, upkeep: {} };
  });

  acceptance(
    "internal-engine",
    "the speech-to-text section shows and changes the pair",
    async () => {
      engineConfig = { ...engineConfig, transcribe_model: "whisper-1" };
      apiMock.list.mockResolvedValue({
        providers: [
          makeProvider({
            name: "B",
            transcribe_default: true,
            models: [
              { id: "whisper-1", modality: "audio" },
              { id: "whisper-2", modality: "audio" },
            ],
          }),
        ],
      });
      renderPage();

      await ready();
      const section = screen.getByTestId("speech-to-text-section");
      expect(within(section).getByText("Speech-to-text")).toBeInTheDocument();
      expect(screen.queryByText("Coffer's model")).not.toBeInTheDocument();
      expect(screen.queryByText("Coffer's engine")).not.toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: /^transcription provider$/i })).toHaveTextContent(
        "B",
      );
      expect(screen.getByRole("combobox", { name: /^transcription model$/i })).toHaveTextContent(
        "whisper-1",
      );
      // No upkeep switch or interval: those live on the Memory page. The one
      // switch left is the price refresh.
      expect(screen.queryAllByRole("switch").filter((s) => s.id !== "price-refresh")).toHaveLength(
        0,
      );

      openSelect(/^transcription model$/i);
      fireEvent.click(screen.getByRole("option", { name: "whisper-2" }));
      await waitFor(() => expect(setSttModel).toHaveBeenCalledWith("whisper-2"));

      // Only the edited value was written — nothing else moved.
      expect(setSttModel).toHaveBeenCalledTimes(1);
      expect(apiMock.setTranscribeDefault).not.toHaveBeenCalled();
      expect(screen.queryByRole("button", { name: /^save$/i })).toBeNull();
    },
  );

  test("an unset picker says what Coffer does without it", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider()] });
    renderPage();
    await ready();

    const stt = screen.getByTestId("model-state");
    expect(stt).toHaveTextContent(/not set/i);
    expect(stt).toHaveTextContent(/reach the agent as audio files/i);
    // Nothing to test while either half is missing.
    expect(screen.getByRole("button", { name: /^test /i })).toBeDisabled();
  });

  acceptance(
    "internal-engine",
    "a failed speech-to-text test leaves the pair as it was",
    async () => {
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

      const state = screen.getByTestId("model-state");
      expect(state).toHaveTextContent(/failing/i);
      expect(state).toHaveTextContent(/connection refused/i);
      // A chat probe would fail on a speech model even on a healthy endpoint.
      expect(testMutate).not.toHaveBeenCalled();
      expect(setSttModel).not.toHaveBeenCalled();
      expect(apiMock.setTranscribeDefault).not.toHaveBeenCalled();
      expect(screen.getByRole("combobox", { name: /^transcription model$/i })).toHaveTextContent(
        "whisper-1",
      );
    },
  );
});
