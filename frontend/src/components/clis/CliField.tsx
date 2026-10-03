// src/components/clis/CliField.tsx — a titled block of a CLI's page (title, one 12px line under it) and a label · value row (boards 4.4.03–4.4.08).
import type { ReactNode } from "react";

export function CliSection({
  title,
  note,
  children,
}: {
  title: string;
  note: string;
  children: ReactNode;
}) {
  return (
    <section className="flex min-w-0 flex-col gap-2" aria-label={title}>
      <div className="flex flex-col gap-0.5">
        <h3 className="text-md font-semibold text-text">{title}</h3>
        <p className="text-xs text-text-muted">{note}</p>
      </div>
      <div className="flex flex-col">{children}</div>
    </section>
  );
}

export function CliField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid min-h-9 grid-cols-[140px_minmax(0,1fr)] items-center gap-3 border-t border-border-subtle">
      <span className="text-sm text-text-muted">{label}</span>
      <span className="flex min-w-0 items-center gap-2 text-sm text-text">{children}</span>
    </div>
  );
}
