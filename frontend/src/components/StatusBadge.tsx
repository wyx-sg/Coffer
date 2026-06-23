// frontend/src/components/StatusBadge.tsx
// One shared status pill for the async-operation tables (distill, KB ingest,
// native-memory import, sync). Each surface maps its own status enum to a
// neutral `tone` + label here, so the colour vocabulary stays consistent:
//   neutral  — not started / idle
//   info     — queued / in-flight, no action needed
//   success  — done / clean
//   warning  — needs attention (e.g. source changed)
//   danger   — failed / error
// A `pulse` flag animates the dot for actively-running work.
import { cn } from "@/lib/utils";

export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

const TONE: Record<StatusTone, { dot: string; text: string; ring: string }> = {
  neutral: { dot: "bg-muted-foreground/50", text: "text-muted-foreground", ring: "border-border" },
  info: { dot: "bg-sky-500", text: "text-sky-700 dark:text-sky-300", ring: "border-sky-500/30" },
  success: {
    dot: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-300",
    ring: "border-emerald-500/30",
  },
  warning: {
    dot: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-300",
    ring: "border-amber-500/30",
  },
  danger: {
    dot: "bg-destructive",
    text: "text-destructive",
    ring: "border-destructive/30",
  },
};

interface Props {
  tone: StatusTone;
  label: string;
  /** Animate the dot — use for actively-running work. */
  pulse?: boolean;
  /** Optional hover title (e.g. an error message). */
  title?: string;
}

export function StatusBadge({ tone, label, pulse, title }: Props) {
  const c = TONE[tone];
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        c.ring,
        c.text,
      )}
    >
      <span className={cn("size-1.5 rounded-full", c.dot, pulse && "animate-pulse")} />
      {label}
    </span>
  );
}
