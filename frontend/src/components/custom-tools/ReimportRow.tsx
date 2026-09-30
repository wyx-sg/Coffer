// src/components/custom-tools/ReimportRow.tsx — one change in Re-import's list: + Add, ~ Changed or
// − Removed, the tool and its request, and what the change means.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

interface Props {
  kind: "add" | "change" | "remove";
  name: string;
  request: string;
  note: string;
}

const TONE = {
  add: "bg-success-soft text-success",
  change: "bg-chip text-text-muted",
  remove: "bg-danger-soft text-danger",
} as const;

export function ReimportRow({ kind, name, request, note }: Props) {
  const { t } = useTranslation();
  return (
    <div className="grid min-h-9 grid-cols-[92px_minmax(0,1fr)_minmax(0,1.2fr)] items-center gap-2.5 border-t border-border-subtle px-2.5 py-1">
      <span
        className={cn(
          "inline-flex h-5 w-fit items-center rounded-sm px-[7px] text-2xs font-semibold",
          TONE[kind],
        )}
      >
        {t(`customTools.reimport.kind.${kind}`)}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate font-mono text-xs text-text">{name}</span>
        <span className="truncate font-mono text-2xs text-text-muted">{request}</span>
      </span>
      <span className="text-xs text-text-muted">{note}</span>
    </div>
  );
}
