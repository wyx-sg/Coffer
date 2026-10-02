// src/components/settings/SettingsLayout.tsx — the one pattern for a stack of titled settings blocks.
//
// Foundations "Forms": a section is its own card (raised surface, hairline
// border, r10) with a header — a 13px semibold title, an optional muted line
// under it, an optional meta/action on the right — a divider, then
// hairline-divided rows. A row is its label with its own helper text on the
// left and its control on the right (`layout="stack"` puts a wide control
// under the label), 56px tall at least. The gap between cards is 24px: wrap
// the stack in `SETTINGS_STACK`. A destructive or rare action is the last
// section. Settings modal tabs and the channel Settings tab are built from
// these two pieces so they read as one surface.
import { useId, type ReactNode } from "react";

import { HelpTip } from "@/components/HelpTip";
import { cn } from "@/lib/utils";

/** The stack of section cards: 24px between them, form width. */
export const SETTINGS_STACK = "flex max-w-form flex-col gap-6";

/** The card surface of a section, for a bespoke block that cannot use `SettingsSection`
 *  (add `p-4` or its own padding). */
export const SETTINGS_CARD = "rounded-xl border border-border bg-surface-raised text-text";

export function SettingsSection({
  title,
  description,
  meta,
  action,
  headingLevel = 3,
  children,
  className,
  testId,
}: {
  title: string;
  /** What the block is for — shown in a "?" tip beside the title, never inline. */
  description?: ReactNode;
  /** Muted text at the right end of the header, before the action (a size). */
  meta?: ReactNode;
  /** The right-hand end of the header: a status, a button. */
  action?: ReactNode;
  /** Heading level under the page's h1 (and a tab's h2): 2 or 3. */
  headingLevel?: 2 | 3;
  children?: ReactNode;
  className?: string;
  testId?: string;
}) {
  const headingId = useId();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section
      aria-labelledby={headingId}
      className={cn(SETTINGS_CARD, className)}
      data-testid={testId}
    >
      <header
        className={cn(
          "flex min-h-control-sm items-center justify-between gap-3 px-4 py-3",
          children ? "border-b border-border-subtle" : null,
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          <Heading id={headingId} className="text-sm font-semibold text-text">
            {title}
          </Heading>
          {description ? <HelpTip>{description}</HelpTip> : null}
        </div>
        {meta || action ? (
          <div className="flex shrink-0 items-center gap-3">
            {meta ? <span className="text-xs text-text-muted">{meta}</span> : null}
            {action}
          </div>
        ) : null}
      </header>
      {children ? (
        <div className="flex flex-col divide-y divide-border-subtle px-4">{children}</div>
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
}) {
  const labelClass = "text-sm font-medium text-text";
  const stack = layout === "stack";
  return (
    <div
      className={cn(
        "flex min-h-setting-row flex-col gap-3 py-2.5",
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
