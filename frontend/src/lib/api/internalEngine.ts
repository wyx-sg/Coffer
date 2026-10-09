// frontend/src/lib/api/internalEngine.ts — Coffer's own operating settings
// (spec internal-engine): the switch and interval of each unattended pass, how
// long ONE model call may take, and the model it transcribes speech with
// (whose endpoint comes from the `transcribe_default` connection).
// Wire types from the internal-engine contract; transport via the typed
// client (.agents/frontend.md §4).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/internal-engine";

export type InternalEngineConfig = components["schemas"]["InternalEngineConfigOut"];
export type UpkeepSetting = components["schemas"]["UpkeepSettingOut"];
export type UpkeepUpdate = components["schemas"]["UpkeepUpdate"];

/** The passes Coffer runs on its own behalf (the memory sync), read off the
 *  contract rather than spelled here, so the two cannot drift. */
export type UpkeepPass = UpkeepUpdate["pass"];

export const internalEngineApi = {
  get: () => unwrap(getApiClient().GET("/internal-engine-config")),
  // One pass per call, each half left alone when it is not sent — so toggling
  // a switch cannot write back a stale copy of another pass's interval.
  setUpkeep: (body: UpkeepUpdate) =>
    unwrap(getApiClient().PUT("/internal-engine-config/upkeep", { body })),
  /** The speech-to-text model; `null` stops transcription, which is a real
   *  answer rather than an unset one. */
  setTranscribeModel: (model: string | null) =>
    unwrap(getApiClient().PUT("/internal-engine-config/transcribe-model", { body: { model } })),
};
