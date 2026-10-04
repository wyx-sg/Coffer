// src/components/agents/list/useRowDialogState.ts — dialog state shared by the cells of one Agents row.
//
// The Agents table draws a row's action button and its ⋯ menu in separate
// columns, so two components of one row each call useAgentRowActions. What
// the button or the menu opens has to be the same dialog, so its state lives
// here, keyed by the agent type, instead of in either component.
import { useCallback, useSyncExternalStore } from "react";

const values = new Map<string, unknown>();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    // No row is on screen any more: a dialog left open does not come back with the next one.
    if (listeners.size === 0) values.clear();
  };
}

export function useRowDialogState<T>(key: string, initial: T): [T, (next: T) => void] {
  const value = useSyncExternalStore(subscribe, () =>
    values.has(key) ? (values.get(key) as T) : initial,
  );
  const set = useCallback(
    (next: T) => {
      if (next === initial) values.delete(key);
      else values.set(key, next);
      emit();
    },
    [key, initial],
  );
  return [value, set];
}
