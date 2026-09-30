// src/components/custom-tools/ToolHeadersField.tsx — a request's headers: the group's auth header shown
// read-only ("from the group"), then this request's own key/value rows.
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthLine } from "./AuthLine";
import type { HeaderRow } from "./toolForm";

interface Props {
  /** The group's auth, when it has a secret bound. */
  auth: { header: string; prefix: string; secret: string } | null;
  headers: HeaderRow[];
  onChange: (headers: HeaderRow[]) => void;
  /** The drawer's wording: "Add header for this request". */
  forThisRequest?: boolean;
}

export function ToolHeadersField({ auth, headers, onChange, forThisRequest = false }: Props) {
  const { t } = useTranslation();
  const set = (i: number, row: HeaderRow) =>
    onChange(headers.map((existing, j) => (j === i ? row : existing)));
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("customTools.editor.headers")}</Label>
      {auth ? (
        <AuthLine
          {...auth}
          trailing={
            <span className="text-xs text-text-muted">{t("customTools.editor.fromGroup")}</span>
          }
        />
      ) : null}
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
            <X aria-hidden />
          </Button>
        </div>
      ))}
      <button
        type="button"
        className="w-fit text-xs font-label text-accent-text hover:underline"
        onClick={() => onChange([...headers, { key: "", value: "" }])}
      >
        {t(forThisRequest ? "customTools.editor.addHeaderThis" : "customTools.editor.addHeader")}
      </button>
    </div>
  );
}
