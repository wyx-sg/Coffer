// src/components/settings/storage/DataBlock.tsx — one kind of data on Settings › Data (design 6.2.07): its name and size, a line on how it is kept, a folder action, then its rows.
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  title: string;
  /** "12.4 MB · 1,382 versions"; null while the sizes load. */
  size: string | null;
  description: ReactNode;
  action?: ReactNode;
  testId: string;
  children?: ReactNode;
}

export function DataBlock({ title, size, description, action, testId, children }: Props) {
  return (
    <section className="flex flex-col gap-0.5" data-testid={testId}>
      <div className="flex min-h-control-sm flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        {size === null ? (
          <Skeleton className="h-4 w-24" />
        ) : (
          <span className="text-xs text-text-muted" data-visual-volatile>
            {size}
          </span>
        )}
        {action ? <div className="ml-auto flex items-center gap-2">{action}</div> : null}
      </div>
      <p className="mb-1 text-xs text-text-muted">{description}</p>
      {children ? <div className="flex flex-col">{children}</div> : null}
    </section>
  );
}
