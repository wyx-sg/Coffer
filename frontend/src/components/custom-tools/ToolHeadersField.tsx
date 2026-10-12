// src/components/custom-tools/ToolHeadersField.tsx — a request's headers as one table (HeaderTable): the chosen
// environment's headers first, read-only, with where they come from ("Environment test", or "Group" when it has one
// environment) and a secret by its name; then this request's own rows, edited in place. A request's own header is a
// plain value: secrets belong to the environment's headers.
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { CustomToolHeaderOut } from "@/lib/api/customTools";
import { HeaderTable, type HeaderTableRow } from "./HeaderTable";
import type { HeaderRow } from "./toolForm";

interface Props {
  /** The chosen environment's headers, shown as what is already added. */
  groupHeaders: readonly CustomToolHeaderOut[];
  /** The group has several environments and these are this one's headers. */
  environment?: string | null;
  headers: HeaderRow[];
  onChange: (headers: HeaderRow[]) => void;
  /** The drawer's wording: "Add header for this request". */
  forThisRequest?: boolean;
}

export function ToolHeadersField({
  groupHeaders,
  headers,
  onChange,
  environment = null,
  forThisRequest = false,
}: Props) {
  const { t } = useTranslation();
  const set = (i: number, row: HeaderRow) =>
    onChange(headers.map((existing, j) => (j === i ? row : existing)));
  const inherited = environment
    ? t("customTools.editor.fromEnvironment", { environment })
    : t("customTools.editor.fromGroup");
  const rows: HeaderTableRow[] = [
    ...groupHeaders.map((h) => ({
      name: h.name,
      value: h.value,
      secret: h.secret,
      source: inherited,
    })),
    ...headers.map((row, i) => ({
      name: row.key,
      value: row.value,
      source: t("customTools.editor.fromTool"),
      edit: {
        onName: (key: string) => set(i, { ...row, key }),
        onValue: (value: string) => set(i, { ...row, value }),
        onRemove: () => onChange(headers.filter((_, j) => j !== i)),
      },
    })),
  ];
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("customTools.editor.headers")}</Label>
      <HeaderTable
        rows={rows}
        sources
        ariaLabel={t("customTools.editor.headers")}
        empty={t("customTools.editor.noHeaders")}
        footer={
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto w-fit px-0 py-0.5"
            onClick={() => onChange([...headers, { key: "", value: "" }])}
          >
            <Plus aria-hidden />
            {t(
              forThisRequest ? "customTools.editor.addHeaderThis" : "customTools.editor.addHeader",
            )}
          </Button>
        }
      />
    </div>
  );
}
