// src/components/secret/useSecretChoices.ts — the stored secrets a secret field offers:
// each Secrets-page name with what uses it, and whether a name is missing here.
import { useMemo } from "react";

import { useTranslation } from "react-i18next";

import { citersOf, displayName, isMissingHere, SECRET_PREFIX } from "./secretRows";
import type { SecretRef } from "@/lib/api/secret";
import { useSecrets } from "@/lib/hooks/useSecrets";

export interface SecretOption {
  /** The id inside `secret/<id>`: what a config cites. */
  name: string;
  /** What a person sees and searches: the label, else a readable default. */
  display: string;
  description: string | null;
  usedBy: number;
  row: SecretRef;
}

export function useSecretChoices() {
  const { t } = useTranslation();
  const unnamed = t("secrets.unnamed");
  const query = useSecrets();
  const options = useMemo<SecretOption[]>(
    () =>
      (query.data?.refs ?? [])
        .filter((r) => r.ref.startsWith(SECRET_PREFIX) && !isMissingHere(r))
        .map((row) => ({
          name: row.ref.slice(SECRET_PREFIX.length),
          display: displayName(row, unnamed),
          description: row.description ?? null,
          usedBy: citersOf(row).length,
          row,
        }))
        .sort((a, b) => a.display.localeCompare(b.display)),
    [query.data, unnamed],
  );
  /** Names that exist; a chosen name outside it is Missing (once loaded). */
  const names = useMemo(() => new Set(options.map((o) => o.name)), [options]);
  /** The row behind a name, including one cited but not stored here. A value with a `/` is
   *  a whole store ref (a field that may cite any secret, like sync's push token), since a
   *  standalone name never holds one. */
  const rowOf = (name: string) => {
    const ref = name.includes("/") ? name : `${SECRET_PREFIX}${name}`;
    return query.data?.refs.find((r) => r.ref === ref);
  };
  /** What a chosen secret is called: its display name, else the placeholder. */
  const displayOf = (name: string) => {
    const row = rowOf(name);
    return row ? displayName(row, unnamed) : unnamed;
  };
  return {
    options,
    names,
    rowOf,
    displayOf,
    loaded: query.data !== undefined,
    isLoading: query.isLoading,
  };
}
