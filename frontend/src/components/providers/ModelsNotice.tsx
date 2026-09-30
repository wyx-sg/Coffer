// src/components/providers/ModelsNotice.tsx — a notice above the Models list: the listing failed, or listed nothing.
import { CircleAlert, Inbox, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  tone: "error" | "neutral";
  title: string;
  body: string;
  action: string;
  onAction: () => void;
}

export function ModelsNotice({ tone, title, body, action, onAction }: Props) {
  const Icon = tone === "error" ? CircleAlert : Inbox;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-xl px-4 py-3",
        tone === "error" ? "bg-danger-soft" : "border border-border-subtle bg-surface-sunken",
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          tone === "error" ? "text-danger" : "text-text-muted",
        )}
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{title}</span>
        <span className="break-words text-xs text-text-muted">{body}</span>
      </div>
      <Button variant="outline" size="sm" onClick={onAction}>
        <RefreshCw aria-hidden /> {action}
      </Button>
    </div>
  );
}
