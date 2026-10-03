// src/components/providers/ProblemBox.tsx — the box a provider's section shows for what is wrong in it.
//
// Three looks, one shape (icon, title, one sentence, then its own actions):
// `danger` is Endpoint's Unreachable / Key rejected (a filled box), `error` is
// Models' listing failure (outlined, red sentence) and `neutral` is Models'
// "listed nothing" (outlined, quiet). The box never repeats a button that sits
// beside it — Models' Refresh is in its title.
import type { ReactNode } from "react";
import { CircleAlert, Inbox } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
  tone: "danger" | "error" | "neutral";
  title: string;
  body: ReactNode;
  children?: ReactNode;
}

export function ProblemBox({ tone, title, body, children }: Props) {
  const Icon = tone === "neutral" ? Inbox : CircleAlert;
  return (
    <div
      role={tone === "neutral" ? "status" : "alert"}
      className={cn(
        "flex items-start gap-2.5 rounded-lg px-3.5 py-3",
        tone === "danger" ? "bg-danger-soft" : "border border-border-subtle bg-surface-raised",
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          tone === "neutral" ? "text-text-muted" : "text-danger",
        )}
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{title}</span>
        <span
          className={cn(
            "break-words text-xs",
            tone === "error" ? "text-danger" : "text-text-muted",
          )}
        >
          {body}
        </span>
        {children ? <div className="mt-2 flex flex-wrap items-center gap-2">{children}</div> : null}
      </div>
    </div>
  );
}
