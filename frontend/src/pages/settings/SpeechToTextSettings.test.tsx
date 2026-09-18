// Settings → Engine → Speech to text: the connection and model Coffer
// transcribes voice with.
//
// The card's whole job is to make an OFF state legible. Transcription has two
// halves — a connection flagged `transcribe_default` and a model — and no
// fallback to the engine's connection, so a vault with neither half set
// transcribes nothing and hands the agent the audio file untouched. That is the
// safe default, not a fault, and these assert that the card says so in words
// rather than rendering two empty dropdowns and leaving the reader to guess.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

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
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ mutate: vi.fn(), isPending: false }),
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
    credential_ref: "provider/acme/key",
    compatible_agents: ["codex"],
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

beforeEach(() => {
  providers = [makeProvider({ name: "a" }), makeProvider({ name: "b" })];
  config = { transcribe_model: null };
});
afterEach(() => vi.clearAllMocks());

describe("SpeechToTextSettings", () => {
  test("with no connection marked, it says transcription is off and what off means", () => {
    // Not an error state: the recording simply stays on the machine.
    render(<SpeechToTextSettings />);

    expect(screen.getByText("Transcription is off.")).toBeInTheDocument();
    expect(screen.getByText(/never leaves this machine/i)).toBeInTheDocument();
  });

  test("a connection marked but no model chosen is still off", () => {
    // Both halves are needed, and neither substitutes for the other.
    providers = [makeProvider({ name: "a", transcribe_default: true })];
    render(<SpeechToTextSettings />);

    expect(screen.getByText("Transcription is off.")).toBeInTheDocument();
  });

  test("with both halves chosen it says transcription is on", () => {
    providers = [makeProvider({ name: "a", transcribe_default: true })];
    config = { transcribe_model: "whisper-1" };
    render(<SpeechToTextSettings />);

    expect(screen.getByText("Transcription is on.")).toBeInTheDocument();
    expect(screen.queryByText("Transcription is off.")).toBeNull();
  });

  test("the card names a second connection rather than borrowing the engine's", () => {
    // The reason the flag exists at all: a chat gateway commonly serves no
    // transcription endpoint, so nothing falls back to the engine's connection.
    render(<SpeechToTextSettings />);

    expect(screen.getByRole("combobox", { name: /transcription provider/i })).toBeInTheDocument();
    expect(screen.getByText(/serves no transcription endpoint at all/i)).toBeInTheDocument();
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
});
