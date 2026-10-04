// src/components/agents/bulk/BulkFailures.tsx — what a bulk run could not do, by name.
//
// The error block of a partial result: a title saying how many went through
// ("Adopted 1 of 3"), then one line per failure — the item's name and the
// reason. The same block sits in a bulk dialog (the confirm button then reads
// Retry and sends only these) and, for a bulk with no dialog, under the bar.
import { AlertTriangle } from "lucide-react";

import type { BulkFailure } from "@/lib/hooks/useBulkRun";

interface Props<T> {
  title: string;
  failures: readonly BulkFailure<T>[];
  nameOf: (item: T) => string;
}

export function BulkFailures<T>({ title, failures, nameOf }: Props<T>) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5" role="alert">
      <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 stroke-[1.75] text-danger" />
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-sm font-label text-text">{title}</span>
        <ul className="flex flex-col gap-0.5 text-xs leading-[1.45] text-text-muted">
          {failures.map((failure, index) => (
            <li key={index} className="break-words">
              <span className="font-mono text-text">{nameOf(failure.item)}</span>
              {": "}
              {failure.message}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
