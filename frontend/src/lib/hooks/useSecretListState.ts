// src/lib/hooks/useSecretListState.ts — the Secrets list's filters, sort and view, kept in the URL (view also remembered per browser).
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import {
  listStateParams,
  parseListState,
  type SecretListState,
  type SecretView,
} from "@/lib/secrets/listState";

const VIEW_KEY = "coffer.secrets.view";

// Per-viewer convenience: storage can be blocked, so every access is guarded.
function storedView(): SecretView {
  try {
    return localStorage.getItem(VIEW_KEY) === "owner" ? "owner" : "list";
  } catch {
    return "list";
  }
}

function rememberView(view: SecretView) {
  try {
    localStorage.setItem(VIEW_KEY, view);
  } catch {
    // Not remembered; the URL still carries it.
  }
}

export function useSecretListState() {
  const [params, setParams] = useSearchParams();
  const key = params.toString();
  // Keyed on the string so an unrelated re-render keeps the same object.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const state = useMemo(() => parseListState(params, storedView()), [key]);
  const update = useCallback(
    (patch: Partial<SecretListState>) => {
      const next = { ...state, ...patch };
      if (patch.view) rememberView(patch.view);
      setParams(listStateParams(next, storedView()), { replace: true });
    },
    [state, setParams],
  );
  return { state, update };
}
