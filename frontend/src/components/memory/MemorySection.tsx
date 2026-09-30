// frontend/src/components/memory/MemorySection.tsx — a titled block on the Memory page.
//
// The overview is two such blocks, "Delivered at session start" and
// "Partitions": a small heading, a muted meta line beside it, the content
// under them.
import type { ReactNode } from "react";

interface Props {
  title: string;
  /** Muted text beside the title, e.g. "Last 7 days" or "5 partitions · 79 memories". */
  meta?: ReactNode;
  testId?: string;
  children: ReactNode;
}

export function MemorySection({ title, meta, testId, children }: Props) {
  return (
    <section className="flex flex-col gap-2" data-testid={testId} aria-label={title}>
      <div className="flex min-h-[26px] items-center gap-2">
        <h2 className="text-sm font-semibold text-text">{title}</h2>
        {meta ? <span className="text-xs text-text-muted">{meta}</span> : null}
      </div>
      {children}
    </section>
  );
}
