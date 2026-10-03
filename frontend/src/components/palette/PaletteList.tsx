// src/components/palette/PaletteList.tsx — the palette's listbox: its groups of rows, and the loading, failure, offline and no-results lines.
import { useTranslation } from "react-i18next";

import { NAV_ENTRIES } from "@/lib/navigation";
import { shortcutLabel } from "@/lib/shortcuts";
import { KIND_PAGE, type ObjectKind, type PaletteItem } from "./paletteItems";
import { PaletteRow, StatusLine, type RowVariant } from "./PaletteParts";
import type { PaletteModel } from "./usePaletteModel";

interface Props {
  model: PaletteModel;
  query: string;
  listboxId: string;
  baseId: string;
  selected: number;
  onHover: (index: number) => void;
  onChoose: (item: PaletteItem) => void;
}

function GroupLabel({ id, children }: { id: string; children: string }) {
  return (
    <div id={id} className="px-2.5 pb-1 pt-2 text-2xs font-semibold text-text-subtle">
      {children}
    </div>
  );
}

export function PaletteList({ model, query, listboxId, baseId, ...props }: Props) {
  const { t } = useTranslation();
  // A kind's group carries the name of the sidebar entry its objects live on.
  const kindTitle = (kind: ObjectKind) =>
    t(NAV_ENTRIES.find((e) => e.to === KIND_PAGE[kind])?.labelKey ?? `palette.kind.${kind}`);
  const groupTitle = (key: PaletteModel["groups"][number]["key"]) =>
    key === "best"
      ? t("palette.bestMatch")
      : key === "recent"
        ? t("palette.recent")
        : key === "pages"
          ? t("palette.pages")
          : kindTitle(key);
  const searching = query.trim() !== "";
  const noResults = searching && model.visible.length === 0 && !model.loading;
  let index = 0;

  return (
    <div
      id={listboxId}
      role="listbox"
      aria-label={t("palette.label")}
      className="flex max-h-[420px] min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-2 py-2.5"
    >
      {model.groups.map((group) => {
        const labelId = `${baseId}-group-${group.key}`;
        const variant: RowVariant =
          group.key === "best" ? "best" : group.key === "recent" ? "recent" : "list";
        return (
          <div key={group.key} role="group" aria-labelledby={labelId} className="flex flex-col gap-2.5">
            <GroupLabel id={labelId}>{groupTitle(group.key)}</GroupLabel>
            {group.items.map((item, i) => {
              const at = group.key === "recent" ? group.recent[i]?.at : undefined;
              const row = index;
              index += 1;
              return (
                <PaletteRow
                  key={item.id}
                  item={item}
                  variant={variant}
                  query={query}
                  at={at}
                  index={row}
                  id={`${baseId}-${group.key}-${item.id}`}
                  selected={row === props.selected}
                  onHover={() => row !== props.selected && props.onHover(row)}
                  onChoose={() => props.onChoose(item)}
                />
              );
            })}
          </div>
        );
      })}
      {model.failed.map((kind) => {
        const labelId = `${baseId}-failed-${kind}`;
        return (
          <div key={kind} role="group" aria-labelledby={labelId} className="flex flex-col gap-2.5">
            <GroupLabel id={labelId}>{kindTitle(kind)}</GroupLabel>
            <StatusLine tone="danger">
              {t("palette.failed", { kind: t(`palette.kind.${kind}`) })}
            </StatusLine>
          </div>
        );
      })}
      {model.loading ? <StatusLine>{t("palette.loading")}</StatusLine> : null}
      {noResults ? (
        <div role="status" className="flex flex-col items-center gap-2 px-4 pb-6 pt-7 text-center">
          <span className="text-sm font-label text-text">
            {t("palette.noResults", { query: query.trim() })}
          </span>
          <span className="text-xs text-text-muted">
            {t("palette.noResultsHint", { shortcut: shortcutLabel("k") })}
          </span>
        </div>
      ) : null}
      {model.offline ? <StatusLine>{t("palette.offline")}</StatusLine> : null}
    </div>
  );
}
