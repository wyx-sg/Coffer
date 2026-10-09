// src/components/custom-tools/ToolQueryField.tsx — the query parameters of a tool's path, one key/value row each,
// kept in step with the Request field: the rows are read from the path, and an edit writes the path back. A value
// that is one `{argument}` hole is marked as an argument.
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { holesIn, joinPath, splitPath, type QueryPair } from "@/lib/customTools/requestParts";

interface Props {
  path: string;
  onChange: (path: string) => void;
}

export function ToolQueryField({ path, onChange }: Props) {
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
      {query.map((pair, i) => (
        <div
          key={i}
          className="grid grid-cols-[10rem_minmax(0,1fr)_5.5rem_2rem] items-center gap-2"
        >
          <Input
            className="font-mono"
            value={pair.key}
            placeholder={t("customTools.editor.queryKey")}
            aria-label={t("customTools.editor.queryKey")}
            onChange={(e) => set(i, { ...pair, key: e.target.value })}
          />
          <Input
            className="font-mono"
            value={pair.value}
            placeholder={t("customTools.editor.queryValue")}
            aria-label={t("customTools.editor.queryValueFor", { key: pair.key })}
            onChange={(e) => set(i, { ...pair, value: e.target.value })}
          />
          <span>
            {holesIn(pair.value).length > 0 ? (
              <Badge>{t("customTools.editor.fromArgument")}</Badge>
            ) : null}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={t("customTools.editor.removeQuery", { key: pair.key })}
            onClick={() => write(query.filter((_, j) => j !== i))}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      ))}
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
  );
}
