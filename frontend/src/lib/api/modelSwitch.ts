// frontend/src/lib/api/modelSwitch.ts — request helpers for /api/v1/providers/model-switch/*.
//
// The agent page's Change model dialog reviews what a model change writes
// (`preview`: the files and their diffs, nothing written) and then writes it
// (`apply`, sending back the fingerprints the preview read so a file edited
// since is refused with 409 CONFIG_FILE_STALE).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/provider-switching";

type Schemas = components["schemas"];

export type ModelSwitchIn = Schemas["ModelSwitchIn"];
export type ModelSwitchFile = Schemas["ModelSwitchFile"];

export const modelSwitchApi = {
  preview: (body: ModelSwitchIn) =>
    unwrap(getApiClient().POST("/providers/model-switch/preview", { body })),
  apply: (body: ModelSwitchIn) =>
    unwrap(getApiClient().POST("/providers/model-switch/apply", { body })),
};
