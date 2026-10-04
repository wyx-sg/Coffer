// src/components/custom-tools/ToolHeadersField.tsx — a request's headers: the group's headers shown read-only
// ("Authorization ← 🔑 deploy-token · from the group"), then this request's own key/value rows. A request's own
// header is a plain value: secrets belong to the group's headers.
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CustomToolHeaderOut } from "@/lib/api/customTools";
import { AuthLine } from "./AuthLine";
import type { HeaderRow } from "./toolForm";

interface Props {
  /** The group's headers, shown as what the group already adds. */
  groupHeaders: readonly CustomToolHeaderOut[];
  headers: HeaderRow[];
  onChange: (headers: HeaderRow[]) => void;
  /** The drawer's wording: "Add header for this request". */
  forThisRequest?: boolean;
}

export function ToolHeadersField({
  groupHeaders,
  headers,
  onChange,
  forThisRequest = false,
}: Props) {
  const { t } = useTranslation();
  const set = (i: number, row: HeaderRow) =>
    onChange(headers.map((existing, j) => (j === i ? row : existing)));
  const fromGroup = (
    <span className="text-xs text-text-muted">{t("customTools.editor.fromGroup")}</span>
  );
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("customTools.editor.headers")}</Label>
      {groupHeaders.map((h) =>
        h.secret ? (
          <AuthLine key={h.name} header={h.name} secret={h.secret} trailing={fromGroup} />
        ) : (
          <span key={h.name} className="inline-flex items-center gap-2">
            <span className="font-mono text-xs">
              {h.name}: {h.value}
            </span>
            {fromGroup}
          </span>
        ),
      )}
      {headers.map((row, i) => (
        <div key={i} className="flex gap-2">
          <Input
            className="w-44 font-mono"
            value={row.key}
            placeholder={t("customTools.editor.headerKey")}
            aria-label={t("customTools.editor.headerKey")}
            onChange={(e) => set(i, { ...row, key: e.target.value })}
          />
          <Input
            className="flex-1 font-mono"
            value={row.value}
            placeholder={t("customTools.editor.headerValue")}
            aria-label={t("customTools.editor.headerValue")}
            onChange={(e) => set(i, { ...row, value: e.target.value })}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon-md"
            aria-label={t("customTools.editor.removeHeader")}
            onClick={() => onChange(headers.filter((_, j) => j !== i))}
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
        onClick={() => onChange([...headers, { key: "", value: "" }])}
      >
        <Plus aria-hidden />
        {t(forThisRequest ? "customTools.editor.addHeaderThis" : "customTools.editor.addHeader")}
      </Button>
    </div>
  );
}
