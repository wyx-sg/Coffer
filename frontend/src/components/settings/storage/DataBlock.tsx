// src/components/settings/storage/DataBlock.tsx — one kind of data on Settings › Data (canvas 1.4.11): its name and size, a line on how it is kept, a folder action, then its rows.
import type { ReactNode } from "react";

import { SettingsSection } from "@/components/settings/SettingsLayout";
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
    <SettingsSection
      title={title}
      description={description}
      meta={
        size === null ? <Skeleton className="h-4 w-24" /> : <span data-visual-volatile>{size}</span>
      }
      action={action}
      testId={testId}
    >
      {children}
    </SettingsSection>
  );
}
