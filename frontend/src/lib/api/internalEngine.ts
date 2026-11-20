// frontend/src/lib/api/internalEngine.ts — Coffer's own operating settings
// (spec internal-engine): the model it transcribes speech with (whose endpoint
// comes from the `transcribe_default` connection).
// Wire types from the internal-engine contract; transport via the typed
// client (.agents/frontend.md §4).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/internal-engine";

export type InternalEngineConfig = components["schemas"]["InternalEngineConfigOut"];

export const internalEngineApi = {
  get: () => unwrap(getApiClient().GET("/internal-engine-config")),
  /** The speech-to-text model; `null` stops transcription, which is a real
   *  answer rather than an unset one. */
  setTranscribeModel: (model: string | null) =>
    unwrap(getApiClient().PUT("/internal-engine-config/transcribe-model", { body: { model } })),
};
