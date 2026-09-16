// frontend/src/lib/api/internalEngine.ts — Coffer's own operating settings
// (spec provider-switching amendment 2026-06-22b, E3/E3a): the MODEL its
// internal engine runs (its endpoint + key come from the `internal_default`
// connection), and the switch and interval of every pass it runs unattended.
// Wire types from the provider-switching contract; transport via the shared
// `call` (agents/frontend.md §4).
import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/provider-switching";

export type InternalEngineConfig = components["schemas"]["InternalEngineConfigOut"];
export type UpkeepSetting = components["schemas"]["UpkeepSettingOut"];
export type UpkeepUpdate = components["schemas"]["UpkeepUpdate"];

/** The passes Coffer runs on its own behalf, in the order they run. */
export type UpkeepPass = "aggregate" | "organise" | "tidy";

const PATH = "/internal-engine-config";

export const internalEngineApi = {
  get: () => call<InternalEngineConfig>(PATH),
  setModel: (model: string | null) =>
    call<InternalEngineConfig>(PATH, { method: "PUT", body: { model } }),
  // One pass per call, each half left alone when it is not sent — so toggling
  // a switch cannot write back a stale copy of another pass's interval.
  setUpkeep: (body: UpkeepUpdate) =>
    call<InternalEngineConfig>(`${PATH}/upkeep`, { method: "PUT", body }),
};
