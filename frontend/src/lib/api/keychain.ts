// frontend/src/lib/api/keychain.ts — typed wrappers around the OS-keychain
// endpoints (spec 008). The UI uses these to store provider API keys under a
// stable ref (e.g. `ai/anthropic`); secrets are write-only — the backend never
// echoes a value back, so there is no GET. Callers track "configured" state by
// other means (e.g. the built-in agent's credential_ref).
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

export const keychainApi = {
  // Store `value` under `ref`. Field names match the backend KeychainSetIn body
  // (`ref` + `value`) verbatim.
  set: async (ref: string, value: string): Promise<void> => {
    const { error } = await getApiClient().POST("/keychain", {
      body: { ref, value },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to store secret");
  },

  // Remove `ref`. Idempotent — deleting an absent ref is fine.
  remove: async (ref: string): Promise<void> => {
    const { error } = await getApiClient().DELETE("/keychain/{ref}", {
      params: { path: { ref } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to delete secret");
  },
};
