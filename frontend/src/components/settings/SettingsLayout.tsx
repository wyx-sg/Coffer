// src/components/settings/SettingsLayout.tsx — the one pattern for a stack of titled settings blocks.
//
// The page grammar (Shell · 1.4): a tab opens with its title (h1, 18/650) and
// one muted intro line (`SettingsTabHeader`); below it sit sections 32px
// apart. A section is NOT boxed — a bordered box is for a group of things,
// hairlines alone are for one thing's properties. Its title is 15/600 with an
// optional meta text and action on the same line, the description is one
// muted line directly under the title, and the rows are separated by
// hairlines (one above the first as well). A row is its label (13/500) with
// its own helper text (12 muted) on the left and its control on the right
// (`layout="stack"` puts a wide control under the label), 56px tall at least.
// A tab with a single section prints no section title. Settings modal tabs and
// the channel Settings tab are built from these pieces so they read as one
// surface.
import { useId, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The stack of sections: 32px between them, form width. */
export const SETTINGS_STACK = "flex max-w-form flex-col gap-8";

/** A tab's title and its one intro line — the head of every Settings pane. */
export function SettingsTabHeader({ title, intro }: { title: string; intro: ReactNode }) {
  return (
    <header className="flex flex-col gap-1">
      <h1 className="text-lg font-bold text-text">{title}</h1>
      <p className="text-sm text-text-muted">{intro}</p>
    </header>
  );
}

export function SettingsSection({
  title,
  description,
  meta,
  action,
  headingLevel = 2,
  children,
  className,
  testId,
}: {
  /** Omitted on a tab that has only one section. */
  title?: string;
  /** What the block is for — one muted line under the title. */
  description?: ReactNode;
  /** Muted text at the right end of the title line, before the action (a size). */
  meta?: ReactNode;
  /** The right-hand end of the title line: a status, a button. */
  action?: ReactNode;
  /** Heading level under the tab's h1: 2 or 3. */
  headingLevel?: 2 | 3;
  children?: ReactNode;
  className?: string;
  testId?: string;
}) {
  const headingId = useId();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section
      aria-labelledby={title ? headingId : undefined}
      className={cn("flex flex-col gap-1.5 text-text", className)}
      data-testid={testId}
    >
      {title ? (
        <div className="flex min-h-[26px] items-center gap-3">
          <Heading id={headingId} className="text-md font-semibold text-text">
            {title}
          </Heading>
          {meta || action ? (
            <div className="ml-auto flex shrink-0 items-center gap-3">
              {meta ? <span className="text-xs text-text-muted">{meta}</span> : null}
              {action}
            </div>
          ) : null}
        </div>
      ) : null}
      {description ? <p className="mt-0.5 text-xs text-text-muted">{description}</p> : null}
      {children ? (
        // A tab's only section has no title, so its first row has no hairline above it.
        <div
          className={cn(
            "mt-1 flex flex-col",
            !title && "[&>*:first-child]:border-t-0 [&>*:first-child>*:first-child]:border-t-0",
          )}
        >
          {children}
        </div>
      ) : null}
    </section>
  );
}

export function SettingRow({
  label,
  labelFor,
  description,
  descriptionId,
  status,
  children,
  align = "center",
  layout = "inline",
  indent = false,
}: {
  label: ReactNode;
  /** Id of the control the label names, when there is one control. */
  labelFor?: string;
  description?: ReactNode;
  /** Id for the helper line, for the control's `aria-describedby`. */
  descriptionId?: string;
  /** A line under the description — a status word, a caution. */
  status?: ReactNode;
  /** The control column. */
  children?: ReactNode;
  align?: "center" | "start";
  /** `stack` puts a wide control (a list, a path field) under the label. */
  layout?: "inline" | "stack";
  /** A sub-row of the row above it: inset 16px, its hairline still full width. */
  indent?: boolean;
}) {
  const labelClass = "text-sm font-medium text-text";
  const stack = layout === "stack";
  return (
    <div
      className={cn(
        "flex min-h-setting-row flex-col gap-3 border-t border-border-subtle py-2.5",
        indent && "pl-4",
        stack ? "justify-center" : "sm:flex-row sm:gap-6",
        !stack && (align === "center" ? "sm:items-center" : "sm:items-start"),
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
        {description ? (
          <span id={descriptionId} className="text-xs text-text-muted">
            {description}
          </span>
        ) : null}
        {status}
      </div>
      {children ? (
        <div className={cn("flex flex-wrap items-center gap-2", stack ? "w-full" : "shrink-0")}>
          {children}
        </div>
      ) : null}
    </div>
  );
}
