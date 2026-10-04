// src/lib/hooks/useSearchParamsKeepingState.ts — `useSearchParams` for a detail page that was opened from elsewhere.
//
// react-router's `setSearchParams` navigates without the current history
// state, so picking a file or a tab on a page opened from another page (an
// agent's Skills tab, ...) dropped that state. This setter carries it along unless the caller passes
// its own.
import { useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

type Setter = ReturnType<typeof useSearchParams>[1];

export function useSearchParamsKeepingState(): [URLSearchParams, Setter] {
  const [params, setParams] = useSearchParams();
  const { state } = useLocation();
  const set: Setter = useCallback(
    (next, options) => setParams(next, { state, ...options }),
    [setParams, state],
  );
  return [params, set];
}
