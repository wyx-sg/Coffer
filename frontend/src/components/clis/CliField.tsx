// src/components/clis/CliField.tsx — a titled section of read-only rows on a CLI's page, and one row of it.
import type { ReactNode } from "react";

export function CliSection({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-label">{title}</h3>
      <div className="paper-card divide-y divide-border-subtle">{children}</div>
    </section>
  );
}

interface FieldProps {
  label: ReactNode;
  children: ReactNode;
  /** After the value: a button. */
  trailing?: ReactNode;
}

export function CliField({ label, children, trailing }: FieldProps) {
  return (
    <div className="flex min-h-row flex-wrap items-center gap-3 px-3 py-2">
      <span className="w-32 shrink-0 text-xs text-text-muted">{label}</span>
      <div className="min-w-0 flex-1 text-sm">{children}</div>
      {trailing}
    </div>
  );
}
