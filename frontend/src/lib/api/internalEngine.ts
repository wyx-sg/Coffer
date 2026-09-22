// frontend/src/lib/api/internalEngine.ts — Coffer's own operating settings
// (spec provider-switching amendment 2026-06-22b, E3/E3a): the MODEL its
// internal engine runs (its endpoint + key come from the `internal_default`
// connection), the switch and interval of every pass it runs unattended, how
// long ONE call to that model may take, and the model it transcribes speech
// with (whose endpoint comes from the separate `transcribe_default`
// connection — nothing falls back between the two).
// Wire types from the provider-switching contract; transport via the shared
// `call` (.agents/frontend.md §4).
import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/internal-engine";

export type InternalEngineConfig = components["schemas"]["InternalEngineConfigOut"];
export type UpkeepSetting = components["schemas"]["UpkeepSettingOut"];
export type UpkeepUpdate = components["schemas"]["UpkeepUpdate"];

/**
 * The passes Coffer runs on its own behalf, in the order they run.
 *
 * `curate` was `tidy` until the knowledge layer became two lanes: the pass no
 * longer rewrites the files the user wrote, it reads them and derives the
 * documents agents read (spec knowledge FR-021). Read off the contract rather
 * than spelled here, so the two cannot drift.
 */
export type UpkeepPass = UpkeepUpdate["pass"];

const PATH = "/internal-engine-config";

export const internalEngineApi = {
  get: () => call<InternalEngineConfig>(PATH),
  setModel: (model: string | null) =>
    call<InternalEngineConfig>(PATH, { method: "PUT", body: { model } }),
  // One pass per call, each half left alone when it is not sent — so toggling
  // a switch cannot write back a stale copy of another pass's interval.
  setUpkeep: (body: UpkeepUpdate) =>
    call<InternalEngineConfig>(`${PATH}/upkeep`, { method: "PUT", body }),
  /** Name the one machine allowed to run the curation pass; `null` clears the
   *  owner and returns the vault to curating wherever the setting is read.
   *
   *  Its own call for the reason `setUpkeep` is: one setting per request, so
   *  taking curation over cannot write back a stale copy of a pass's switch.
   *  The id is not checked against the registry here — a vault that has never
   *  converged has no registry and must still be able to name its own
   *  machine. */
  setCurationOwner: (machineId: string | null) =>
    call<InternalEngineConfig>(`${PATH}/curation-owner`, {
      method: "PUT",
      body: { machine_id: machineId },
    }),
  /** Bound one call to Coffer's own model; `null` returns it to the built-in
   *  default, which is the only way back — the server keeps the number. Out of
   *  range is refused rather than clamped, so the caller hears about a typo. */
  setModelTimeout: (seconds: number | null) =>
    call<InternalEngineConfig>(`${PATH}/timeout`, { method: "PUT", body: { seconds } }),
  /** The speech-to-text model; `null` stops transcription, which is a real
   *  answer rather than an unset one. */
  setTranscribeModel: (model: string | null) =>
    call<InternalEngineConfig>(`${PATH}/transcribe-model`, { method: "PUT", body: { model } }),
};
