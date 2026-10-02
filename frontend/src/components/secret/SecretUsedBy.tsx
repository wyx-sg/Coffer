// src/components/secret/SecretUsedBy.tsx — the Used by cell: a count and names, opening a popover of each citer.
//
// Each citer is listed by its kind and current name and opens that resource's
// page (spec web-ui "Manage stored secrets on the Secrets page"). A secret
// nothing uses reads "Nothing".
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { SecretRef } from "@/lib/api/secret";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import { citersOf, displayName, referenceOf, type Citer } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

function CiterName({ citer }: { citer: Citer }) {
  const pageOpen = useKindPageOpen();
  if (!citer.href || !pageOpen(citer.kind))
    return <span className="truncate text-sm text-text">{citer.name}</span>;
  return (
    <Link
      to={citer.href}
      className="truncate text-sm text-text underline-offset-2 hover:underline focus-visible:underline"
    >
      {citer.name}
    </Link>
  );
}

export function SecretUsedBy({ row }: { row: SecretRef }) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  const citers = citersOf(row);
  if (citers.length === 0) {
    return <span className="text-xs text-text-muted">{t("secrets.usedBy.nothing")}</span>;
  }
  const name = displayName(row);
  return (
    <Popover>
      <PopoverTrigger asChild>
        {/* A disclosure of the cell's own content, not a row action: it reads
            as the names it lists, as in the design. */}
        <button
          type="button"
          aria-label={t("secrets.usedBy.trigger", { count: citers.length, name })}
          className="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-text-muted transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-chip px-1.5 text-2xs font-semibold text-text">
            {citers.length}
          </span>
          <span className="truncate text-accent">{citers.map((c) => c.name).join(", ")}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] space-y-2" onClick={(e) => e.stopPropagation()}>
        <p className="text-xs font-semibold text-text">{t("secrets.usedBy.title", { name })}</p>
        <ul className="space-y-1.5">
          {citers.map((citer) => (
            <li key={citer.key} className="flex items-center justify-between gap-3">
              <CiterName citer={citer} />
              <span className="shrink-0 text-xs text-text-muted">{kindLabel(citer.kind)}</span>
            </li>
          ))}
        </ul>
        <p className="border-t border-border-subtle pt-2 text-xs text-text-muted">
          {t("secrets.usedBy.note", { reference: referenceOf(row) })}
        </p>
      </PopoverContent>
    </Popover>
  );
}
