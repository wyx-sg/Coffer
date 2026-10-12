// src/components/custom-tools/HeaderTable.tsx — one look for a request's headers wherever a custom tool shows them
// (the Request tab, the Test tab's request, an environment's card): a bordered table, Name · Value · (Source), one
// row per header. A header read from a secret shows the secret by name with a key, never a value, and its state
// when it is not ready. A row with `edit` is this tool's own header, edited in place; every other row is read-only.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Trash2 } from "lucide-react";

import { SecretName } from "@/components/secret/SecretNameLink";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface HeaderTableRow {
  name: string;
  /** The plain value; null when it comes from a secret. */
  value: string | null;
  secret?: string | null;
  /** The secret's state when it is not set ("missing", "pending_approval", "rejected"). */
  secretState?: string | null;
  /** Where it comes from ("Environment test", "This tool"); shown when the table has a Source column. */
  source?: string;
  /** This row is edited here. */
  edit?: {
    onName: (name: string) => void;
    onValue: (value: string) => void;
    onRemove: () => void;
  };
}

interface Props {
  rows: readonly HeaderTableRow[];
  /** Show the Source column. */
  sources?: boolean;
  ariaLabel: string;
  /** Under the rows, inside the frame: the Add header link. */
  footer?: ReactNode;
  /** Shown in place of the rows when there are none. */
  empty?: ReactNode;
}

/** A cell edited in place: borderless until hovered or focused. Shared with the query table. */
export const CELL_INPUT =
  "h-8 w-full min-w-0 rounded-sm border border-transparent bg-transparent px-2 font-mono text-xs text-text " +
  "placeholder:text-text-subtle hover:border-border focus-visible:border-accent focus-visible:bg-surface-raised " +
  "focus-visible:outline-none";

export function HeaderTable({ rows, sources = false, ariaLabel, footer, empty }: Props) {
  const { t } = useTranslation();
  const cols = sources
    ? "grid-cols-[minmax(8rem,2fr)_minmax(0,3fr)_minmax(6rem,1fr)_2rem]"
    : "grid-cols-[minmax(8rem,2fr)_minmax(0,3fr)_2rem]";
  return (
    <div
      role="table"
      aria-label={ariaLabel}
      className="overflow-hidden rounded-lg border border-border-subtle"
    >
      <div
        role="row"
        className={cn(
          "grid items-center gap-2 border-b border-border-subtle bg-surface-sunken px-3 py-1.5 text-2xs font-semibold text-text-muted",
          cols,
        )}
      >
        <span role="columnheader">{t("customTools.headerTable.name")}</span>
        <span role="columnheader">{t("customTools.headerTable.value")}</span>
        {sources ? <span role="columnheader">{t("customTools.headerTable.source")}</span> : null}
        <span />
      </div>
      {rows.length === 0 && empty ? (
        <p className="px-3 py-2.5 text-xs text-text-muted">{empty}</p>
      ) : null}
      {rows.map((row, i) => (
        <div
          key={`${row.name}-${i}`}
          role="row"
          className={cn(
            "grid min-h-10 items-center gap-2 border-b border-border-subtle px-3 py-1 last:border-b-0",
            cols,
            !row.edit && "bg-surface-sunken/40",
          )}
        >
          {row.edit ? (
            <>
              <span role="cell" className="-ml-2 min-w-0">
                <input
                  className={CELL_INPUT}
                  value={row.name}
                  placeholder={t("customTools.editor.headerKey")}
                  aria-label={t("customTools.editor.headerKey")}
                  onChange={(e) => row.edit?.onName(e.target.value)}
                />
              </span>
              <span role="cell" className="-ml-2 min-w-0">
                <input
                  className={CELL_INPUT}
                  value={row.value ?? ""}
                  placeholder={t("customTools.editor.headerValue")}
                  aria-label={t("customTools.editor.headerValueFor", { name: row.name })}
                  onChange={(e) => row.edit?.onValue(e.target.value)}
                />
              </span>
            </>
          ) : (
            <>
              <span role="cell" className="min-w-0 break-all font-mono text-xs text-text">
                {row.name}
              </span>
              <span role="cell" className="flex min-w-0 flex-wrap items-center gap-2">
                {row.secret ? (
                  <SecretValue secret={row.secret} state={row.secretState ?? null} />
                ) : (
                  <span className="min-w-0 break-all font-mono text-xs text-text-muted">
                    {row.value}
                  </span>
                )}
              </span>
            </>
          )}
          {sources ? (
            <span
              role="cell"
              className="min-w-0 truncate text-xs text-text-muted"
              title={row.source}
            >
              {row.source}
            </span>
          ) : null}
          <span role="cell" className="flex justify-end">
            {row.edit ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("customTools.editor.removeHeaderNamed", { name: row.name })}
                onClick={row.edit.onRemove}
              >
                <Trash2 aria-hidden />
              </Button>
            ) : null}
          </span>
        </div>
      ))}
      {footer ? <div className="border-t border-border-subtle px-3 py-1.5">{footer}</div> : null}
    </div>
  );
}

function SecretValue({ secret, state }: { secret: string; state: string | null }) {
  const { t } = useTranslation();
  const ref = secret.startsWith("secret/") ? secret : `secret/${secret}`;
  const notReady = state !== null && state !== "present" && state !== "none";
  return (
    <>
      <span className="inline-flex h-[22px] min-w-0 items-center gap-1.5 rounded-md border border-border-subtle bg-surface-raised px-[7px] text-xs text-text">
        <KeyRound className="size-3 shrink-0 text-text-muted" aria-hidden />
        <span className="truncate">
          <SecretName secretRef={ref} />
        </span>
      </span>
      {notReady ? (
        <span className="text-xs text-warning">
          {t(`customTools.preview.secretState.${state}`)}
        </span>
      ) : null}
    </>
  );
}
