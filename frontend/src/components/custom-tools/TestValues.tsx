// src/components/custom-tools/TestValues.tsx — the Test tab's sample values: one box per named input, two columns,
// its name (a red * when required) and type beside it; with no inputs, a line saying so.
import { useTranslation } from "react-i18next";

import type { ArgRow } from "@/lib/customTools/schemaArgs";

interface Props {
  inputs: ArgRow[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}

export function TestValues({ inputs, values, onChange }: Props) {
  const { t } = useTranslation();
  if (inputs.length === 0)
    return <p className="text-xs text-text-muted">{t("customTools.test.noInputs")}</p>;
  return (
    <div className="grid gap-x-6 gap-y-2 md:grid-cols-2">
      {inputs.map((row) => (
        <label
          key={row.name}
          className="grid grid-cols-[9rem_minmax(0,1fr)] items-center gap-2 font-mono text-xs"
        >
          <span className="min-w-0 truncate" title={row.name}>
            {row.name}
            {row.required ? <span className="text-danger">*</span> : null}{" "}
            <span className="text-2xs text-text-muted">
              {row.type === "other" ? row.rawType : row.type}
            </span>
          </span>
          <input
            className="h-control-md min-w-0 rounded-md border border-border bg-surface-raised px-2 font-mono text-xs text-text placeholder:text-text-subtle focus-visible:border-accent focus-visible:outline-none"
            aria-label={t("customTools.test.valueFor", { name: row.name })}
            placeholder={row.type === "other" && row.rawType === "array" ? '["…"]' : undefined}
            value={values[row.name] ?? ""}
            onChange={(e) => onChange({ ...values, [row.name]: e.target.value })}
          />
        </label>
      ))}
    </div>
  );
}
