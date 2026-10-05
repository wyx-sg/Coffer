// src/components/custom-tools/VariableRows.tsx — an environment's variables: name · value · delete. Plain text
// only (a tool uses one as `{env:NAME}`); a credential belongs in a secret header, never here.
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { VariableRow } from "./environmentVariables";

interface Props {
  rows: VariableRow[];
  onChange: (rows: VariableRow[]) => void;
}

const GRID = "grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_26px] items-center gap-2";

export function VariableRows({ rows, onChange }: Props) {
  const { t } = useTranslation();
  const update = (i: number, patch: Partial<VariableRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, i) => (
        <div key={i} className={GRID}>
          <Input
            className="font-mono"
            aria-label={t("customTools.environments.variableName")}
            placeholder="region"
            value={row.key}
            onChange={(e) => update(i, { key: e.target.value })}
          />
          <Input
            className="font-mono"
            aria-label={t("customTools.environments.variableValue", { name: row.key })}
            value={row.value}
            onChange={(e) => update(i, { value: e.target.value })}
          />
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("customTools.environments.removeVariable", { name: row.key })}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      ))}
      <Button
        variant="ghost"
        size="sm"
        className="self-start"
        onClick={() => onChange([...rows, { key: "", value: "" }])}
      >
        <Plus aria-hidden />
        {t("customTools.environments.addVariable")}
      </Button>
    </div>
  );
}
