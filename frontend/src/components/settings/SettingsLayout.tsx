// src/components/settings/SettingsLayout.tsx — the section and row rhythm of a Settings pane.
//
// Foundations "Forms": a section is a 13px semibold heading (optionally a
// muted line under it) over hairline-divided rows; a row is its label and
// description on the left and its control on the right, 56px tall at least.
// Settings › Security and the Coffer's model section of Settings › General
// are built from these two pieces so they read as one surface.
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
    <section className={cn("flex flex-col gap-0.5", className)} data-testid={testId}>
      <h3 className="flex min-h-control-sm items-center text-sm font-semibold text-text">
        {title}
      </h3>
      {description ? <p className="mb-1 text-xs text-text-muted">{description}</p> : null}
      <div className="flex flex-col">{children}</div>
    </section>
  );
}

export function SettingRow({
  label,
  labelFor,
  description,
  status,
  children,
  align = "center",
}: {
  label: ReactNode;
  /** Id of the control the label names, when there is one control. */
  labelFor?: string;
  description?: ReactNode;
  /** A line under the description — a status word, a caution. */
  status?: ReactNode;
  /** The control column. */
  children?: ReactNode;
  align?: "center" | "start";
}) {
  const labelClass = "text-sm font-medium text-text";
  return (
    <div
      className={cn(
        "flex min-h-setting-row flex-col gap-3 border-t border-border-subtle py-2.5 first:border-t-0 sm:flex-row sm:gap-6",
        align === "center" ? "sm:items-center" : "sm:items-start",
      )}
    >
      <div className="flex min-w-0 grow flex-col gap-0.5">
        {labelFor ? (
          <label htmlFor={labelFor} className={labelClass}>
            {label}
          </label>
        ) : (
          <span className={labelClass}>{label}</span>
        )}
        {description ? <span className="text-xs text-text-muted">{description}</span> : null}
        {status}
      </div>
      {children ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div>
      ) : null}
    </div>
  );
}
