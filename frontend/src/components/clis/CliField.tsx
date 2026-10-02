// src/components/clis/CliField.tsx — a titled section of read-only rows on a CLI's page, and one row of it.
import type { ReactNode } from "react";

import { Section } from "@/components/Section";

export function CliSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Section title={title} gap="snug" labelled>
      <div className="paper-card divide-y divide-border-subtle">{children}</div>
    </Section>
  );
}

interface FieldProps {
  label: ReactNode;
  children: ReactNode;
}

export function CliField({ label, children }: FieldProps) {
  return (
    <div className="flex min-h-row flex-wrap items-center gap-3 px-3 py-2">
      <span className="inline-flex min-w-32 shrink-0 items-center text-xs text-text-muted">
        {label}
      </span>
      <div className="min-w-0 flex-1 text-sm">{children}</div>
    </div>
  );
}
