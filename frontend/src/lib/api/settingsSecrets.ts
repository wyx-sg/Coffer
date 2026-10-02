// src/lib/api/settingsSecrets.ts — request functions for the secret-handling settings.
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type SecretSettings = components["schemas"]["SecretSettingsOut"];
export type SecretSettingsIn = components["schemas"]["SecretSettingsIn"];

export const secretSettingsApi = {
  get: (): Promise<SecretSettings> => unwrap(getApiClient().GET("/settings/secrets")),
  update: (body: SecretSettingsIn): Promise<SecretSettings> =>
    unwrap(getApiClient().PUT("/settings/secrets", { body })),
};
