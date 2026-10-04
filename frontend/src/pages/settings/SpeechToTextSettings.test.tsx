// frontend/src/pages/settings/SpeechToTextSettings.test.tsx
//
// Settings › General › Coffer's model › Speech to text: the connection and
// model Coffer transcribes voice with.
//
// The picker's first job is to make an unset state legible. Transcription has two
// halves — a connection flagged `transcribe_default` and a model — and no
// fallback to the engine's connection, so a vault with neither half set
// transcribes nothing and hands the agent the audio file untouched. That is the
// safe default, not a fault, and these assert that the card says so in words
// rather than rendering two empty dropdowns and leaving the reader to guess.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { SpeechToTextSettings } from "./SpeechToTextSettings";
import type { InternalEngineConfig } from "@/lib/api/internalEngine";
import type { Provider } from "@/lib/api/providers";

const setConnection = vi.fn();
const setModel = vi.fn();

// Read inside the hook stubs rather than at factory time, so the mock factory
// (hoisted above these declarations) never touches them in the temporal dead
// zone.
let providers: Provider[] = [];
let config: Partial<InternalEngineConfig> = {};

vi.mock("@/lib/hooks/useProviders", () => ({
  useProviders: () => ({ data: providers }),
  useSetTranscribeDefaultProvider: () => ({ mutate: setConnection, isPending: false }),
}));
vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: config }),
  useSetTranscribeModel: () => ({ mutate: setModel, isPending: false }),
}));
// The model list probes the endpoint when a connection curates nothing; the
// tests that care about the list curate one instead, so the probe never fires.
const listMutate = vi.fn();
const chatProbe = vi.fn();
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ mutate: listMutate, isPending: false }),
  useTestConnection: () => ({ mutate: chatProbe, isPending: false }),
}));

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
    protocol: "openai",
    base_url: "https://gw/openai",
    secret_ref: "provider/acme/key",
    local_runtime: null,
    compatible_agents: ["codex"],
    title: null,
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

beforeEach(() => {
  providers = [makeProvider({ name: "a" }), makeProvider({ name: "b" })];
  config = { transcribe_model: null };
});
afterEach(() => vi.clearAllMocks());

describe("SpeechToTextSettings", () => {
  test("with no connection marked, it reads as not set and says what that means", () => {
    // Not an error state: the agent simply receives the audio file.
    render(<SpeechToTextSettings />);

    const state = screen.getByTestId("model-state");
    expect(state).toHaveTextContent(/not set/i);
    expect(state).toHaveTextContent(/reach the agent as audio files/i);
  });

  test("a connection marked but no model chosen is still not set", () => {
    // Both halves are needed, and neither substitutes for the other.
    providers = [makeProvider({ name: "a", transcribe_default: true })];
    render(<SpeechToTextSettings />);

    expect(screen.getByTestId("model-state")).toHaveTextContent(/not set/i);
  });

  test("with both halves chosen it reads as set", () => {
    providers = [makeProvider({ name: "a", transcribe_default: true })];
    config = { transcribe_model: "whisper-1" };
    render(<SpeechToTextSettings />);

    expect(screen.getByTestId("model-state")).toHaveTextContent(/^set$/i);
    expect(screen.getByRole("button", { name: /test speech to text/i })).toBeEnabled();
  });

  test("the picker names a second connection rather than borrowing the engine's", () => {
    // The reason the flag exists at all: a chat gateway commonly serves no
    // transcription endpoint, so nothing falls back to the engine's connection.
    providers = [makeProvider({ name: "a", internal_default: true })];
    render(<SpeechToTextSettings />);

    expect(screen.getByRole("combobox", { name: /transcription provider/i })).toHaveTextContent(
      "Choose a provider",
    );
  });

  test("choosing a connection marks that one as where speech goes", () => {
    render(<SpeechToTextSettings />);

    openSelect(/transcription provider/i);
    // The option READS as the connection's name and CARRIES its uid, which is
    // what the flag is written against.
    fireEvent.click(screen.getByRole("option", { name: "b" }));

    expect(setConnection).toHaveBeenCalledWith(uidFor("b"));
  });

  test("the model dropdown offers the connection's speech models, not its chat ones", () => {
    // One base URL and key answer for chat and speech alike, so the list is
    // narrowed by what KIND of model each curated entry is.
    providers = [
      makeProvider({
        name: "a",
        transcribe_default: true,
        models: [
          { id: "gpt-4o", modality: "text" },
          { id: "whisper-1", modality: "audio" },
        ],
      }),
    ];
    render(<SpeechToTextSettings />);

    openSelect(/transcription model/i);
    expect(screen.getByRole("option", { name: "whisper-1" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "gpt-4o" })).toBeNull();
  });

  test("choosing a model turns transcription on", () => {
    providers = [
      makeProvider({
        name: "a",
        transcribe_default: true,
        models: [{ id: "whisper-1", modality: "audio" }],
      }),
    ];
    render(<SpeechToTextSettings />);

    openSelect(/transcription model/i);
    fireEvent.click(screen.getByRole("option", { name: "whisper-1" }));

    expect(setModel).toHaveBeenCalledWith("whisper-1");
  });

  test("switching the model off is an option, not something only the CLI can do", () => {
    providers = [
      makeProvider({
        name: "a",
        transcribe_default: true,
        models: [{ id: "whisper-1", modality: "audio" }],
      }),
    ];
    config = { transcribe_model: "whisper-1" };
    render(<SpeechToTextSettings />);

    openSelect(/transcription model/i);
    fireEvent.click(screen.getByRole("option", { name: /do not transcribe/i }));

    expect(setModel).toHaveBeenCalledWith(null);
  });

  test("a saved model the endpoint cannot list still reads as chosen", () => {
    // Otherwise a working setting would look like one nobody made.
    providers = [
      makeProvider({
        name: "a",
        transcribe_default: true,
        models: [{ id: "whisper-1", modality: "audio" }],
      }),
    ];
    config = { transcribe_model: "some-private-stt" };
    render(<SpeechToTextSettings />);

    expect(screen.getByRole("combobox", { name: /transcription model/i })).toHaveTextContent(
      "some-private-stt",
    );
  });

  describe("Test asks the endpoint for its model list, never a chat request", () => {
    /** A chosen pair on a curated connection, with the listing the endpoint answers. */
    function testWith(listing: {
      models: { id: string; modality: string }[];
      message: string;
      reachable?: boolean;
    }) {
      providers = [
        makeProvider({
          name: "a",
          transcribe_default: true,
          models: [{ id: "whisper-1", modality: "audio" }],
        }),
      ];
      config = { transcribe_model: "whisper-1" };
      listMutate.mockImplementation((_probe, opts) => opts?.onSuccess?.(listing));
      render(<SpeechToTextSettings />);
      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /test speech to text/i }));
      });
      expect(listMutate).toHaveBeenCalledWith(
        { provider: "openai", base_url: "https://gw/openai", secret_ref: "provider/acme/key" },
        expect.anything(),
      );
      expect(chatProbe).not.toHaveBeenCalled();
      return screen.getByTestId("model-state");
    }

    test("a listing that names the chosen model reads as answering", () => {
      const state = testWith({
        models: [{ id: "whisper-1", modality: "audio" }],
        message: "",
      });
      expect(state).toHaveTextContent(/answering/i);
    });

    test("a listing without the chosen model fails inline", () => {
      const state = testWith({ models: [{ id: "tts-1", modality: "audio" }], message: "" });
      expect(state).toHaveTextContent(/failing/i);
      expect(state).toHaveTextContent("The endpoint didn't list whisper-1");
      expect(setModel).not.toHaveBeenCalled();
    });

    test("an endpoint that answers but lists nothing is reachable, not failing", () => {
      const state = testWith({
        models: [],
        message: "the endpoint listed no models",
        reachable: true,
      });
      expect(state).toHaveTextContent(/reachable/i);
      expect(state).toHaveTextContent(/couldn't be checked/i);
      expect(state).not.toHaveTextContent(/failing/i);
    });

    test("an endpoint that could not be listed fails with its own message", () => {
      const state = testWith({ models: [], message: "401 invalid api key", reachable: false });
      expect(state).toHaveTextContent(/failing/i);
      expect(state).toHaveTextContent("401 invalid api key");
    });
  });
});
