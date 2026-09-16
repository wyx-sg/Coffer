// frontend/src/lib/hooks/useDebouncedValue.ts
//
// One shared debounce for the search boxes over paged lists. DataTable owns the
// page and page-size state itself, so a list surface needs nothing from here
// but the delay before a typed filter becomes a request.
import { useEffect, useState } from "react";

// Debounce (ms) before the filter value is applied, so typing doesn't fire a
// request per keystroke.
const FILTER_DEBOUNCE_MS = 300;

/** Hold a value back until the user stops changing it. */
export function useDebouncedValue<T>(value: T, delayMs: number = FILTER_DEBOUNCE_MS): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return settled;
}
