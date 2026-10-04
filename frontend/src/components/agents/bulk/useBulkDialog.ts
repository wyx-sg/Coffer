// src/components/agents/bulk/useBulkDialog.ts — the state of one bulk confirmation over an agent's own items.
//
// Opening it freezes the selected rows (the bar, and with it the selection's
// owner, may go away while the dialog is up). Confirming runs the batch one
// request after another; when every one went through the dialog closes, the
// caller reports and the selection clears. When some failed the dialog stays
// open on their names and its confirm button sends only those again.
import { useCallback, useState } from "react";
import type { QueryKey } from "@tanstack/react-query";

import { useBulkRun, type BulkFailure } from "@/lib/hooks/useBulkRun";

interface Open<T> {
  items: T[];
  clear: () => void;
}

export function useBulkDialog<T>(invalidate: QueryKey[]) {
  const { run, isPending } = useBulkRun(invalidate);
  const [open, setOpen] = useState<Open<T> | null>(null);
  const [failures, setFailures] = useState<BulkFailure<T>[]>([]);

  const start = useCallback((items: T[], clear: () => void) => {
    setFailures([]);
    setOpen({ items, clear });
  }, []);

  const close = useCallback(() => {
    setOpen(null);
    setFailures([]);
  }, []);

  /** Runs the batch (or, after a partial result, only its failures). */
  const confirm = async (
    runOne: (item: T) => Promise<unknown>,
    onAllDone: (count: number) => void,
  ) => {
    if (!open) return;
    const targets = failures.length > 0 ? failures.map((f) => f.item) : open.items;
    const result = await run(targets, runOne);
    if (result.failures.length === 0) {
      onAllDone(open.items.length);
      open.clear();
      close();
    } else {
      setFailures(result.failures);
    }
  };

  return {
    /** The rows the dialog was opened on; null while it is closed. */
    items: open?.items ?? null,
    failures,
    isPending,
    start,
    close,
    confirm,
  };
}
