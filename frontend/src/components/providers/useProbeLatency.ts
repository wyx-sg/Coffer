// src/components/providers/useProbeLatency.ts — how long the open provider's endpoint probe took, in ms.
//
// The probe answers no timing of its own, so the page times it: from the
// moment the query starts fetching to the moment it settles — the same hop
// the Test dialogs measure. Null until a probe has finished.
import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

export function useProbeLatency(
  uid: string | undefined,
  endpoint: Pick<UseQueryResult, "isFetching" | "dataUpdatedAt">,
) {
  const started = useRef<number | null>(null);
  const [ms, setMs] = useState<number | null>(null);
  const { isFetching, dataUpdatedAt } = endpoint;

  // Another provider: forget the last one's timing.
  useEffect(() => {
    started.current = null;
    setMs(null);
  }, [uid]);

  useEffect(() => {
    if (isFetching) {
      started.current ??= performance.now();
    } else if (started.current !== null) {
      setMs(Math.max(1, Math.round(performance.now() - started.current)));
      started.current = null;
    }
  }, [uid, isFetching, dataUpdatedAt]);

  return ms;
}
