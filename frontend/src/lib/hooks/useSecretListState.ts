// src/lib/hooks/useSecretListState.ts — the Secrets list's search and status, kept in the URL.
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { parseListState, withListState, type SecretListState } from "@/lib/secrets/listState";

export function useSecretListState() {
  const [params, setParams] = useSearchParams();
  const key = params.toString();
  // Keyed on the string so an unrelated re-render keeps the same object.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const state = useMemo(() => parseListState(params), [key]);
  const update = useCallback(
    (patch: Partial<SecretListState>) =>
      setParams((prev) => withListState(prev, { ...parseListState(prev), ...patch }), {
        replace: true,
      }),
    [setParams],
  );
  const clear = useCallback(() => update({ q: "", status: "all" }), [update]);
  return { state, update, clear };
}
