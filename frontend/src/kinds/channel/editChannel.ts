// frontend/src/kinds/channel/editChannel.ts
// Apply plumbing for EditChannelDialog: rotated secrets are written to their
// existing credential refs FIRST (so the channel keeps working off the same
// refs), then the resource config is PATCHed (bound agent / SeaTalk app id).
// Unlike registration there is nothing to roll back — overwriting a ref's
// value and PATCHing a live resource are both in-place updates.
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

import type { ChannelPlan } from "./schema";

// The resource kind for channels. Inlined (not imported from useChannels) so
// this module stays free of a hook → editChannel → hook import cycle.
const CHANNEL_KIND = "channel";

async function writeSecret(ref: string, value: string): Promise<void> {
  const { error } = await getApiClient().POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "credential write failed");
}

async function patchConfig(name: string, config: Record<string, unknown>): Promise<void> {
  const { error } = await getApiClient().PATCH("/resources/{kind}/{name}", {
    params: { path: { kind: CHANNEL_KIND, name } },
    body: { config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "update failed");
}

/**
 * Rotate the changed secrets, then PATCH the config. Returns the name.
 * Secrets-first matches registration: a config that references a ref whose
 * value just changed must see the new value, never a stale one.
 */
export async function applyChannelEdit(plan: ChannelPlan): Promise<string> {
  for (const s of plan.secrets) {
    await writeSecret(s.ref, s.value);
  }
  await patchConfig(plan.name, plan.config);
  return plan.name;
}
