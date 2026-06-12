// frontend/src/kinds/channel/registerChannel.ts
// Registration plumbing for AddChannelDialog: secrets are written to the
// credential store FIRST (registration probes the refs — FR-001), then the
// resource is registered; on failure the just-written secrets are rolled
// back so nothing orphaned stays behind.
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

import type { ChannelPlan } from "./schema";

async function writeSecret(ref: string, value: string): Promise<void> {
  const { error } = await getApiClient().POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "credential write failed");
}

/** Best-effort rollback of secrets written before a failed registration. */
async function rollbackSecrets(refs: string[]): Promise<void> {
  for (const ref of refs) {
    try {
      await getApiClient().DELETE("/credentials/{ref}", { params: { path: { ref } } });
    } catch (e) {
      console.warn(`[AddChannelDialog] rollback delete failed for ${ref}:`, e);
    }
  }
}

async function registerResource(plan: ChannelPlan): Promise<void> {
  const { error } = await getApiClient().POST("/resources", {
    body: { kind: "channel", name: plan.name, config: plan.config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
}

/**
 * Fail BEFORE any secret write when the name is taken: writing first would
 * overwrite the live channel's secret and then roll it back (deleting it),
 * leaving the existing channel dead on its next restart.
 */
async function assertNameAvailable(name: string): Promise<void> {
  const { data } = await getApiClient().GET("/resources/{kind}/{name}", {
    params: { path: { kind: "channel", name } },
  });
  if (data) {
    throwApiError(
      { error: { code: "RESOURCE_ALREADY_EXISTS", message: `channel ${name} already exists` } },
      "RESOURCE_ALREADY_EXISTS",
      "name already in use",
    );
  }
}

/** Secrets-then-resource registration with rollback; returns the name. */
export async function createChannel(plan: ChannelPlan): Promise<string> {
  await assertNameAvailable(plan.name);
  const written: string[] = [];
  try {
    for (const s of plan.secrets) {
      await writeSecret(s.ref, s.value);
      written.push(s.ref);
    }
    await registerResource(plan);
  } catch (e) {
    await rollbackSecrets(written);
    throw e;
  }
  return plan.name;
}
