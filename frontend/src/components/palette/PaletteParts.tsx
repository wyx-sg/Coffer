// src/components/palette/PaletteParts.tsx — the palette's small pieces: a row, a status line and a key hint.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { LucideIcon } from "lucide-react";

import { Kbd } from "@/components/ui/kbd";
import { relativeTime } from "@/lib/clis/format";
import { NAV_ENTRIES, SETTINGS_TABS } from "@/lib/navigation";
import { shortcutLabel } from "@/lib/shortcuts";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { KIND_PAGE, splitMatch, type PaletteItem } from "./paletteItems";

/** The sidebar icon of the page an entry is, or of the page its kind lives on. */
function iconOf(item: PaletteItem): LucideIcon | undefined {
  if (item.kind === "settings") {
    const tab = item.target.type === "settings" ? item.target.tab : undefined;
    return SETTINGS_TABS.find((s) => s.id === tab)?.icon;
  }
  const route = item.kind === "page" && item.target.type === "route" ? item.target.to : null;
  const to = route ?? (item.kind === "page" ? undefined : KIND_PAGE[item.kind]);
  return NAV_ENTRIES.find((entry) => entry.to === to)?.icon;
}

/** `text` with the part the query matched in bold. */
function Highlighted({ text, query }: { text: string; query: string }) {
  const parts = splitMatch(text, query);
  if (!parts) return <>{text}</>;
  return (
    <>
      {parts[0]}
      <b className="font-bold">{parts[1]}</b>
      {parts[2]}
    </>
  );
}

/** Where the row sits decides its meta: "best" names an object's kind inline,
 *  "recent" says when a page was opened, "list" repeats kind and status. */
export type RowVariant = "best" | "recent" | "list";

interface RowProps {
  item: PaletteItem;
  variant: RowVariant;
  query: string;
  /** When a Recent entry was chosen. */
  at?: string;
  index: number;
  id: string;
  selected: boolean;
  onHover: () => void;
  onChoose: () => void;
}

/** One entry: kind icon, label (the match in bold), an inline kind word in
 *  Best match, and the meta on the right. */
export function PaletteRow({ item, variant, query, at, index, id, selected, ...on }: RowProps) {
  const { t, i18n } = useTranslation();
  const Icon = iconOf(item);
  const isPage = item.kind === "page" || item.kind === "settings";
  const kindWord = t(`palette.kind.${isPage ? "page" : item.kind}`);
  const status = item.status ? (
    <span className={toneTextClass(item.status.tone)}>
      {t(`palette.status.${item.status.key}`)}
    </span>
  ) : null;
  const meta: ReactNode[] = [];
  if (variant === "best") {
    if (isPage) meta.push(kindWord);
    else if (status) meta.push(status);
    if (!isPage && item.note) meta.push(item.note);
  } else if (isPage) {
    if (variant === "recent" && at) meta.push(relativeTime(at, i18n.language));
    else if (item.id === "settings-general") meta.push(shortcutLabel(","));
  } else {
    meta.push(kindWord);
    if (item.note) meta.push(item.note);
    if (status) meta.push(status);
  }
  return (
    <div
      id={id}
      role="option"
      aria-selected={selected}
      data-index={index}
      onMouseMove={on.onHover}
      onMouseDown={(event) => event.preventDefault()}
      onClick={on.onChoose}
      className={cn(
        "flex h-control-lg shrink-0 cursor-pointer items-center gap-2.5 rounded-md px-2.5",
        selected && "bg-surface-selected",
      )}
    >
      {Icon ? <Icon className="size-[15px] shrink-0 text-text-subtle" aria-hidden /> : null}
      <span className="min-w-0 truncate text-sm text-text">
        <span data-testid="palette-row-label">
          <Highlighted text={item.label} query={query} />
        </span>
        {variant === "best" && !isPage ? (
          <span className="ml-1.5 text-xs text-text-muted">{kindWord}</span>
        ) : null}
      </span>
      {item.detail ? (
        <span className="min-w-0 truncate font-mono text-xs text-text-subtle">
          <Highlighted text={item.detail} query={query} />
        </span>
      ) : null}
      {meta.length > 0 ? (
        <span className="ml-auto shrink-0 whitespace-nowrap pl-2 text-xs text-text-subtle">
          {meta.map((part, i) => (
            <span key={i}>
              {i > 0 ? " · " : null}
              {part}
            </span>
          ))}
        </span>
      ) : null}
    </div>
  );
}

export function StatusLine({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "danger";
}) {
  return (
    <p
      role="status"
      className={cn(
        "flex min-h-control-lg items-center px-2.5 text-xs",
        tone === "danger" ? "text-danger" : "text-text-subtle",
      )}
    >
      {children}
    </p>
  );
}

export function Hint({ keys, label }: { keys: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Kbd>{keys}</Kbd>
      {label}
    </span>
  );
}
