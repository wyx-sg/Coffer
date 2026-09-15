// frontend/src/lib/api/internalEngine.ts — the single, global internal-engine
// model selection (spec provider-switching amendment 2026-06-22b). The internal
// engine takes its endpoint + key from the `internal_default` connection but its
// MODEL from this singleton. Wire type from the provider-switching contract;
// transport via the shared `call` (agents/frontend.md §4).
import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/provider-switching";

export type InternalEngineConfig = components["schemas"]["InternalEngineConfigOut"];

const PATH = "/internal-engine-config";

export const internalEngineApi = {
  get: () => call<InternalEngineConfig>(PATH),
  setModel: (model: string | null) =>
    call<InternalEngineConfig>(PATH, { method: "PUT", body: { model } }),
};
