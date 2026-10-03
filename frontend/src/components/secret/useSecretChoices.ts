// src/components/secret/useSecretChoices.ts — the stored secrets a secret field offers:
// each Secrets-page name with what uses it, and whether a name is missing here.
import { useMemo } from "react";

import { citersOf, isMissingHere, SECRET_PREFIX } from "./secretRows";
import type { SecretRef } from "@/lib/api/secret";
import { useSecrets } from "@/lib/hooks/useSecrets";

export interface SecretOption {
  name: string;
  usedBy: number;
  row: SecretRef;
}

export function useSecretChoices() {
  const query = useSecrets();
  const options = useMemo<SecretOption[]>(
    () =>
      (query.data?.refs ?? [])
        .filter((r) => r.ref.startsWith(SECRET_PREFIX) && !isMissingHere(r))
        .map((row) => ({
          name: row.ref.slice(SECRET_PREFIX.length),
          usedBy: citersOf(row).length,
          row,
        }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [query.data],
  );
  /** Names that exist; a chosen name outside it is Missing (once loaded). */
  const names = useMemo(() => new Set(options.map((o) => o.name)), [options]);
  /** The row behind a name, including one cited but not stored here. */
  const rowOf = (name: string) => query.data?.refs.find((r) => r.ref === `${SECRET_PREFIX}${name}`);
  return { options, names, rowOf, loaded: query.data !== undefined, isLoading: query.isLoading };
}
