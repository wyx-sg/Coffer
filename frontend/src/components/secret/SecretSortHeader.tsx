// src/components/secret/SecretSortHeader.tsx — a sortable column header: its title and the direction it is sorted in.
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { SecretListState, SortKey } from "@/lib/secrets/listState";

interface Props {
  column: SortKey;
  title: string;
  state: SecretListState;
  onSort: (column: SortKey) => void;
}

export function SecretSortHeader({ column, title, state, onSort }: Props) {
  const { t } = useTranslation();
  const active = state.sort === column;
  const Icon = !active ? ChevronsUpDown : state.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      aria-label={t("secrets.sort", { column: title })}
      data-sort={active ? state.dir : undefined}
      onClick={() => onSort(column)}
      className="-mx-1 inline-flex items-center gap-1 rounded-sm px-1 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
    >
      {title}
      <Icon className={active ? "size-3 text-text" : "size-3 opacity-50"} aria-hidden />
    </button>
  );
}
