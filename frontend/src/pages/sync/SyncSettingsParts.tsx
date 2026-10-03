// frontend/src/pages/sync/SyncSettingsParts.tsx — the sections and hairline rows
// of first-run setup (6.4.20) and the Remote tab (6.4.27).
//
// A section is a 15/600 title with one 12px line under it; its rows are a
// label (13/500) with an optional hint on the left and the control in a
// 360px column on the right, each row split from the next by a hairline —
// no card around any of it.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function SettingsSection({
  title,
  description,
  children,
  className,
  testId,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section className={cn("flex flex-col", className)} data-testid={testId}>
      <div className="flex flex-col gap-0.5 pb-1">
        <h2 className="text-md font-semibold text-text">{title}</h2>
        {description ? <p className="text-xs text-text-muted">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function SettingsRow({
  label,
  labelFor,
  hint,
  hintId,
  control,
  wide = true,
}: {
  label: ReactNode;
  labelFor?: string;
  hint?: ReactNode;
  hintId?: string;
  /** The control; sits in a 360px column unless `wide` is false (a switch or a button). */
  control: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="flex min-h-[52px] items-center gap-6 border-b border-border-subtle py-2.5">
      <div className="flex min-w-0 grow flex-col gap-0.5">
        {labelFor ? (
          <label htmlFor={labelFor} className="text-sm font-medium text-text">
            {label}
          </label>
        ) : (
          <span className="text-sm font-medium text-text">{label}</span>
        )}
        {hint ? (
          <span id={hintId} className="text-xs text-text-muted">
            {hint}
          </span>
        ) : null}
      </div>
      <div className={cn("flex shrink-0 justify-end", wide && "w-[360px]")}>{control}</div>
    </div>
  );
}
