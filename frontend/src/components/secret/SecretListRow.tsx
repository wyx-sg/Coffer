// src/components/secret/SecretListRow.tsx — one secret in the Secrets list pane.
//
// The display name (its label, else a readable default — never a hex id) on one line, with no
// description (that is on its page); on the right, a status word when this Mac has no value or a destination waits for
// approval, and how many things use it. The checkbox feeds the selection bar; like the other
// library lists it shows on hover or focus, and on every row while any is ticked.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import type { SecretItem } from "./secretListView";
import { citersOf } from "./secretRows";

interface Props {
  item: SecretItem;
  to: string;
  current: boolean;
  /** Any row is ticked: every checkbox shows. */
  selecting: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

export function SecretListRow({ item, to, current, selecting, checked, onCheckedChange }: Props) {
  const { t } = useTranslation();
  const { row } = item;
  const uses = citersOf(row).length;
  return (
    <li
      className={cn(
        "group flex items-center gap-2 rounded-lg pl-2.5 transition-colors duration-fast",
        current ? "bg-surface-selected" : "hover:bg-surface-hover",
      )}
    >
      <span
        className={cn(
          "shrink-0 items-center",
          selecting || checked
            ? "inline-flex"
            : "hidden group-focus-within:inline-flex group-hover:inline-flex",
        )}
      >
        <Checkbox
          checked={checked}
          onChange={(e) => onCheckedChange(e.target.checked)}
          aria-label={t("secrets.row.select", { name: item.short })}
        />
      </span>
      <Link
        to={to}
        aria-current={current ? "page" : undefined}
        className="flex min-h-[52px] min-w-0 flex-1 items-center gap-2.5 rounded-lg py-2 pr-2.5 text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
      >
        <span className="min-w-0 flex-1 truncate text-sm font-label">{item.short}</span>
        <span className="flex shrink-0 flex-col items-end gap-0.5">
          {item.missing ? <StatusWord tone="err">{t("secrets.row.missing")}</StatusWord> : null}
          {item.pending ? <StatusWord tone="warn">{t("secrets.row.pending")}</StatusWord> : null}
          <span className="text-xs text-text-muted">
            {uses === 0 ? t("secrets.usedBy.nothing") : t("secrets.list.usedBy", { count: uses })}
          </span>
        </span>
      </Link>
    </li>
  );
}
