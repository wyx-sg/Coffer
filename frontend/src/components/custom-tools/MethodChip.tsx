// src/components/custom-tools/MethodChip.tsx — an HTTP method as a short mono chip, tinted by what it does the way
// API clients colour them: reads (GET) green, writes (POST, PUT, PATCH) amber, DELETE red, anything else grey.
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = {
  GET: "bg-success-soft text-success",
  POST: "bg-warning-soft text-warning",
  PUT: "bg-warning-soft text-warning",
  PATCH: "bg-warning-soft text-warning",
  DELETE: "bg-danger-soft text-danger",
};

export function MethodChip({ method, className }: { method: string; className?: string }) {
  const upper = method.toUpperCase();
  return (
    <span
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center rounded-sm px-1.5 font-mono text-2xs font-semibold",
        TONE[upper] ?? "bg-chip text-text-muted",
        className,
      )}
    >
      {upper}
    </span>
  );
}
