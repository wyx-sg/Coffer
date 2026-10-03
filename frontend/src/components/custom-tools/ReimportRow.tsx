// src/components/custom-tools/ReimportRow.tsx — one change in Re-import's list: a tick for an operation to add
// (a write starts unticked), the tool and its request, and its + Add / ~ Modify / − Remove chip. Choosing the
// row opens its spec text on the right.
import { useTranslation } from "react-i18next";

import { OpChip } from "@/components/change-preview/OpChip";
import { Checkbox } from "@/components/ui/checkbox";
import type { ReimportItem } from "@/lib/customTools/reimport";
import { cn } from "@/lib/utils";

interface Props {
  item: ReimportItem;
  selected: boolean;
  /** Add rows only. */
  ticked?: boolean;
  onTick?: (on: boolean) => void;
  onSelect: () => void;
}

export function ReimportRow({ item, selected, ticked = false, onTick, onSelect }: Props) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        "flex min-h-9 items-center gap-2 rounded-md px-2 py-1",
        selected ? "bg-surface-raised ring-1 ring-border" : "hover:bg-surface-hover",
      )}
    >
      {item.op === "add" ? (
        <Checkbox
          checked={ticked}
          aria-label={t("customTools.reimport.add", { name: item.name })}
          onChange={(e) => onTick?.(e.target.checked)}
        />
      ) : (
        <span className="size-[15px] shrink-0" aria-hidden />
      )}
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-2 text-left"
      >
        <span className="flex min-w-0 flex-1 flex-col gap-px">
          <span className="truncate font-mono text-xs text-text">{item.name}</span>
          <span className="truncate font-mono text-2xs text-text-muted">{item.request}</span>
        </span>
        <OpChip op={item.op} size="sm" />
      </button>
    </div>
  );
}
