// src/components/custom-tools/ToolQueryField.tsx — the query parameters of a tool's path, in the same table frame
// as its headers (HeaderTable): one key/value row each, kept in step with the Request field — the rows are read
// from the path, and an edit writes the path back. A value that names an input (`{region}`) says which, and the
// chip opens that input on the Inputs tab.
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { holesIn, joinPath, splitPath, type QueryPair } from "@/lib/customTools/requestParts";
import { cn } from "@/lib/utils";
import { CELL_INPUT } from "./HeaderTable";

interface Props {
  path: string;
  onChange: (path: string) => void;
  /** Open the Inputs tab at this input. */
  onShowInput?: (name: string) => void;
}

const COLS = "grid-cols-[minmax(8rem,2fr)_minmax(0,3fr)_minmax(6rem,1fr)_2rem]";
export function ToolQueryField({ path, onChange, onShowInput }: Props) {
  const { t } = useTranslation();
  const { base, query } = splitPath(path);
  const write = (next: QueryPair[]) => onChange(joinPath(base, next));
  const set = (i: number, pair: QueryPair) => write(query.map((p, j) => (j === i ? pair : p)));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <Label>{t("customTools.editor.query")}</Label>
        <span className="ml-auto text-xs text-text-muted">{t("customTools.editor.queryHelp")}</span>
      </div>
      <div
        role="table"
        aria-label={t("customTools.editor.query")}
        className="overflow-hidden rounded-lg border border-border-subtle"
      >
        <div
          role="row"
          className={cn(
            "grid items-center gap-2 border-b border-border-subtle bg-surface-sunken px-3 py-1.5 text-2xs font-semibold text-text-muted",
            COLS,
          )}
        >
          <span role="columnheader">{t("customTools.editor.queryKey")}</span>
          <span role="columnheader">{t("customTools.editor.queryValue")}</span>
          <span role="columnheader">{t("customTools.editor.queryFills")}</span>
          <span />
        </div>
        {query.length === 0 ? (
          <p className="px-3 py-2.5 text-xs text-text-muted">{t("customTools.editor.noQuery")}</p>
        ) : null}
        {query.map((pair, i) => (
          <div
            key={i}
            role="row"
            className={cn(
              "grid min-h-10 items-center gap-2 border-b border-border-subtle px-3 py-1",
              COLS,
            )}
          >
            <span role="cell" className="-ml-2 min-w-0">
              <input
                className={CELL_INPUT}
                value={pair.key}
                placeholder={t("customTools.editor.queryKey")}
                aria-label={t("customTools.editor.queryKey")}
                onChange={(e) => set(i, { ...pair, key: e.target.value })}
              />
            </span>
            <span role="cell" className="-ml-2 min-w-0">
              <input
                className={CELL_INPUT}
                value={pair.value}
                placeholder={t("customTools.editor.queryValue")}
                aria-label={t("customTools.editor.queryValueFor", { key: pair.key })}
                onChange={(e) => set(i, { ...pair, value: e.target.value })}
              />
            </span>
            <span role="cell" className="flex min-w-0 flex-wrap gap-1">
              {holesIn(pair.value).map((name) => (
                <button
                  key={name}
                  type="button"
                  className="inline-flex h-5 max-w-full items-center truncate rounded-sm bg-accent-soft px-1.5 font-mono text-2xs text-accent-text hover:underline"
                  onClick={() => onShowInput?.(name)}
                >
                  {t("customTools.editor.fromInput", { name })}
                </button>
              ))}
            </span>
            <span role="cell" className="flex justify-end">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("customTools.editor.removeQuery", { key: pair.key })}
                onClick={() => write(query.filter((_, j) => j !== i))}
              >
                <Trash2 aria-hidden />
              </Button>
            </span>
          </div>
        ))}
        <div className="px-3 py-1.5">
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto w-fit px-0 py-0.5"
            onClick={() => onChange(`${path}${path.includes("?") ? "&" : "?"}param=`)}
          >
            <Plus aria-hidden />
            {t("customTools.editor.addQuery")}
          </Button>
        </div>
      </div>
    </div>
  );
}
