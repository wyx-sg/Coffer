// src/lib/hooks/useSecretNames.ts — the names of the secrets stored on the Secrets page, for a secret picker.
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { secretsApi } from "@/lib/api/secret";
import { secretsListKey } from "@/lib/api/queryKeys";

/** A standalone secret's ref: `secret/<name>`. */
const SECRET_PREFIX = "secret/";

/** Every stored standalone secret, by its Secrets-page name, sorted. Presence
 *  only — no value is read. */
export function useSecretNames() {
  const query = useQuery({ queryKey: secretsListKey, queryFn: secretsApi.list });
  const names = useMemo(
    () =>
      (query.data?.refs ?? [])
        .filter((ref) => ref.present && ref.ref.startsWith(SECRET_PREFIX))
        .map((ref) => ref.ref.slice(SECRET_PREFIX.length))
        .sort((a, b) => a.localeCompare(b)),
    [query.data],
  );
  return { ...query, names };
}
