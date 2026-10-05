// src/components/secret/SecretOverview.tsx — the Overview tab: where the secret lives and everything that uses it.
//
// The reference (the id every config cites) and, for a standalone secret, its URI, each with
// Copy; whether this Mac holds the value; whether other local processes can read it; when it was
// created and last used; and Used by — each citer with its kind, current name and slot, the
// approval it holds or waits for, and a link to its page (spec web-ui "Manage stored secrets on
// the Secrets page"). No value is ever shown here.
import { Check, Copy } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { RelativeTime } from "@/components/RelativeTime";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import type { SecretRef } from "@/lib/api/secret";
import { useCopyText } from "@/lib/hooks/useCopyText";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import { kindMeta } from "@/lib/overview/kinds";
import { cn } from "@/lib/utils";
import { citersOf, isMissingHere, standaloneName, type Citer } from "./secretRows";
import { shortDate } from "./secretTimes";
import { useKindLabel } from "./useKindLabel";

const TERM = "flex h-7 items-center text-xs text-text-muted";
/** Every value cell is one row tall, so a row with a Copy button lines up with one without. */
const DEF = "flex h-7 min-w-0 items-center gap-1.5 text-xs text-text";

function CopyLine({ text, label }: { text: string; label: string }) {
  const { copied, copy } = useCopyText();
  return (
    <>
      <code className="min-w-0 truncate font-mono text-xs text-text" title={text}>
        {text}
      </code>
      <Button variant="ghost" size="icon-sm" aria-label={label} onClick={() => copy(text)}>
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      </Button>
    </>
  );
}

function UsedByLine({ citer, row }: { citer: Citer; row: SecretRef }) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  const pageOpen = useKindPageOpen();
  const Icon = kindMeta(citer.kind).icon;
  const bindings = row.bindings.filter(
    (b) => b.destination_kind === citer.kind && b.destination_uid === citer.uid,
  );
  const binding = bindings[0];
  const body = (
    <>
      <Icon className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
      <span className="min-w-0 truncate text-xs text-text">
        {/* The sync remote is one setting, not a named resource: it reads as the page it lives on. */}
        {citer.kind === "sync_remote" ? kindLabel(citer.kind) : citer.name}
      </span>
      <span className="min-w-0 flex-1 truncate text-xs text-text-subtle">
        {binding?.slot ?? kindLabel(citer.kind)}
      </span>
      {binding ? (
        <StatusWord tone={binding.status === "pending" ? "warn" : "ok"}>
          {binding.status === "pending" ? t("secrets.row.pending") : t("secrets.detail.approved")}
        </StatusWord>
      ) : null}
    </>
  );
  const line = "flex h-7 items-center gap-2 rounded-md px-2";
  if (!citer.href || !pageOpen(citer.kind)) return <li className={line}>{body}</li>;
  return (
    <li>
      <Link
        to={citer.href}
        className={cn(
          line,
          "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
        )}
      >
        {body}
      </Link>
    </li>
  );
}

export function SecretOverview({ row }: { row: SecretRef }) {
  const { t, i18n } = useTranslation();
  const missing = isMissingHere(row);
  const citers = citersOf(row);
  // A destination waiting for approval that the secret is not cited by yet.
  const waiting = row.bindings.filter(
    (b) =>
      b.status === "pending" &&
      !row.cited_by.some((c) => c.kind === b.destination_kind && c.uid === b.destination_uid),
  );
  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-[112px_minmax(0,1fr)] gap-x-3 gap-y-1">
        <dt className={TERM}>{t("secrets.detail.reference")}</dt>
        <dd className={DEF}>
          <CopyLine text={row.ref} label={t("secrets.detail.copyReference")} />
        </dd>
        {standaloneName(row.ref) !== null && row.uri ? (
          <>
            <dt className={TERM}>{t("secrets.detail.uri")}</dt>
            <dd className={DEF}>
              <CopyLine text={row.uri} label={t("secrets.detail.copyUri")} />
            </dd>
          </>
        ) : null}
        <dt className={TERM}>{t("secrets.detail.value")}</dt>
        <dd className={DEF}>
          {missing ? (
            <StatusWord tone="err">{t("secrets.row.missing")}</StatusWord>
          ) : (
            <StatusWord tone="ok">{t("secrets.detail.present")}</StatusWord>
          )}
        </dd>
        {row.readable_by_local_processes ? (
          <>
            <dt className={TERM}>{t("secrets.detail.access")}</dt>
            <dd className={DEF}>{t("secrets.row.localReadable")}</dd>
          </>
        ) : null}
        <dt className={TERM}>{t("secrets.cols.created")}</dt>
        <dd className={DEF}>{row.created_at ? shortDate(row.created_at, i18n.language) : "—"}</dd>
        <dt className={TERM}>{t("secrets.cols.lastUsed")}</dt>
        <dd className={DEF}>
          {row.last_used_at ? <RelativeTime iso={row.last_used_at} /> : t("secrets.time.never")}
        </dd>
      </dl>

      <section className="space-y-1.5" aria-label={t("secrets.usedBy.title")}>
        <h3 className="text-xs font-semibold text-text">{t("secrets.usedBy.title")}</h3>
        {citers.length === 0 && waiting.length === 0 ? (
          <p className="text-xs text-text-muted">{t("secrets.usedBy.nothing")}</p>
        ) : (
          <ul className="-mx-2">
            {citers.map((c) => (
              <UsedByLine key={c.key} citer={c} row={row} />
            ))}
            {waiting.map((b) => (
              <li
                key={`${b.destination_kind}:${b.destination_uid}:${b.slot}`}
                className="flex h-7 items-center gap-2 px-2"
              >
                <span className="min-w-0 truncate text-xs text-text">{b.destination_uid}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-text-subtle">{b.slot}</span>
                <StatusWord tone="warn">{t("secrets.row.pending")}</StatusWord>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
