// src/components/custom-tools/ToolHeadersField.tsx — a request's headers: the group's auth header shown
// read-only, then this request's own key/value rows.
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { authLine } from "@/lib/customTools/drafts";
import type { HeaderRow } from "./toolForm";

interface Props {
  group: CustomToolGroup;
  headers: HeaderRow[];
  onChange: (headers: HeaderRow[]) => void;
}

export function ToolHeadersField({ group, headers, onChange }: Props) {
  const { t } = useTranslation();
  const auth = group.auth;
  const set = (i: number, row: HeaderRow) =>
    onChange(headers.map((existing, j) => (j === i ? row : existing)));
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("customTools.editor.headers")}</Label>
      {auth?.secret ? (
        <p className="rounded-md bg-surface-sunken px-2.5 py-1.5 font-mono text-xs text-text-muted">
          {t("customTools.editor.groupAuth", {
            line: authLine(auth.header, auth.prefix),
            secret: auth.secret,
          })}
        </p>
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
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-fit"
        onClick={() => onChange([...headers, { key: "", value: "" }])}
      >
        <Plus aria-hidden />
        {t("customTools.editor.addHeader")}
      </Button>
    </div>
  );
}
