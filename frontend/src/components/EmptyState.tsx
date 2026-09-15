// src/components/EmptyState.tsx — the shared "nothing here yet" surface.
// A centred, bordered card with an optional icon, a title, optional
// description and an optional call-to-action, so every list / not-found /
// zero-result screen reads the same.
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  icon?: LucideIcon;
  title: string;
  description?: string;
  /** Usually a Button (or Button asChild + Link). */
  action?: ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-border bg-card px-6 py-12 text-center">
      {Icon ? (
        <Icon className="mb-3 size-8 text-muted-foreground" strokeWidth={1.5} aria-hidden />
      ) : null}
      <p className="text-base font-medium text-foreground">{title}</p>
      {description ? (
        <p className="mt-1 max-w-prose text-sm text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
