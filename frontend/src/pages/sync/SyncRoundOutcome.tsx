// frontend/src/pages/sync/SyncRoundOutcome.tsx
//
// How a round ended, in the Rounds table's "Round" cell: the status dot, the
// word beside it, and the muted clause that tells it apart. Rounds that did
// nothing read quietly so the ones that did stand out.
import { toneDotClass, toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { statusTone } from "./syncRoundStatus";

export function SyncRoundOutcome({
  status,
  main,
  detail,
}: {
  status: string;
  main: string;
  detail: string | null;
}) {
  const tone = statusTone(status);
  const quiet = tone === "muted";
  return (
    <span className="block min-w-0 truncate text-xs">
      <span
        className={cn(
          "inline-flex items-center gap-[7px] whitespace-nowrap",
          quiet ? "text-text-subtle" : "text-text-muted",
          tone === "error" && toneTextClass(tone),
        )}
      >
        <span aria-hidden className={cn("size-[7px] shrink-0 rounded-full", toneDotClass(tone))} />
        {main}
      </span>
      {detail ? <span className="text-text-muted"> · {detail}</span> : null}
    </span>
  );
}
