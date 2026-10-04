// src/components/secret/SecretUsedBy.tsx — the Used by cell: the first two names and "+N", opening a popover of everything that reads the secret.
//
// The popover (Foundations 0.4.01, 300 wide) always carries a "Find…" search that matches a
// name or a type, shows six rows and scrolls inside, grouped by type then name. A row opens that
// resource's page (spec web-ui "Manage stored secrets on the Secrets page"); one whose feature
// is off is a plain row. A secret nothing uses reads "Nothing".
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { SecretRef } from "@/lib/api/secret";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import { kindMeta } from "@/lib/overview/kinds";
import { cn } from "@/lib/utils";
import { citersOf, displayName, referenceOf, type Citer } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

/** Names the cell spells out before "+N". */
const NAMES_SHOWN = 2;

/** The popover's type blocks, in order; any other type follows. */
const KIND_ORDER = [
  "provider",
  "mcp_server",
  "custom_tool",
  "channel",
  "skill",
  "knowledge",
  "memory",
];
const rank = (kind: string) => {
  const i = KIND_ORDER.indexOf(kind);
  return i === -1 ? KIND_ORDER.length : i;
};

function CiterRow({ citer, kindLabel }: { citer: Citer; kindLabel: string }) {
  const pageOpen = useKindPageOpen();
  const Icon = kindMeta(citer.kind).icon;
  const body = (
    <>
      <Icon className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
      <span className="min-w-0 flex-1 truncate text-sm text-text">{citer.name}</span>
      <span className="shrink-0 text-xs text-text-subtle">{kindLabel}</span>
    </>
  );
  const row = "flex h-8 items-center gap-2 rounded-md px-2";
  if (!citer.href || !pageOpen(citer.kind)) return <li className={row}>{body}</li>;
  return (
    <li>
      <Link
        to={citer.href}
        className={cn(
          row,
          "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
        )}
      >
        {body}
      </Link>
    </li>
  );
}

export function SecretUsedBy({ row }: { row: SecretRef }) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  const [q, setQ] = useState("");
  const citers = useMemo(() => citersOf(row), [row]);
  const sorted = useMemo(
    () =>
      [...citers].sort(
        (a, b) =>
          rank(a.kind) - rank(b.kind) ||
          a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
      ),
    [citers],
  );
  if (citers.length === 0) {
    return <span className="text-xs text-text-muted">{t("secrets.usedBy.nothing")}</span>;
  }
  const name = displayName(row);
  const needle = q.trim().toLowerCase();
  const shown = needle ? sorted.filter((c) => c.name.toLowerCase().includes(needle)) : sorted;
  const rest = citers.length - NAMES_SHOWN;
  return (
    <Popover onOpenChange={(open) => !open && setQ("")}>
      <PopoverTrigger asChild>
        {/* A disclosure of the cell's own content, not a row action: it reads as the names it lists. */}
        <button
          type="button"
          aria-label={t("secrets.usedBy.trigger", { count: citers.length, name })}
          className="-mx-1.5 inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-xs transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring data-[state=open]:bg-surface-hover"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="truncate text-accent-text">
            {citers
              .slice(0, NAMES_SHOWN)
              .map((c) => c.name)
              .join(", ")}
          </span>
          {rest > 0 ? <span className="shrink-0 text-text-subtle">+{rest}</span> : null}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] space-y-2" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-xs font-semibold text-text">{t("secrets.usedBy.title")}</p>
          <p className="truncate font-mono text-xs text-text-muted">{name}</p>
        </div>
        <Input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("secrets.usedBy.find")}
          aria-label={t("secrets.usedBy.find")}
          className="h-8 text-xs"
        />
        <ul className="max-h-[192px] overflow-y-auto">
          {shown.map((citer) => (
            <CiterRow key={citer.key} citer={citer} kindLabel={kindLabel(citer.kind)} />
          ))}
        </ul>
        <p className="border-t border-border-subtle pt-2 text-xs text-text-muted">
          {t("secrets.usedBy.note", { reference: referenceOf(row) })}
        </p>
      </PopoverContent>
    </Popover>
  );
}
