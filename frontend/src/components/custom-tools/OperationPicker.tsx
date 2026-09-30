// src/components/custom-tools/OperationPicker.tsx — Import step 1's Operations: the spec's operations by
// tag, each one ticked to become a tool (reads start ticked, operations that change data do not).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import type { OpenApiReading } from "@/lib/api/customTools";
import { operationChangesData, sectionOf, type Operation } from "@/lib/customTools/operations";
import { cn } from "@/lib/utils";
import { defaultPicks } from "./addFlow";

interface Props {
  reading: OpenApiReading;
  picked: string[];
  onPicked: (picked: string[]) => void;
}

const METHOD_TONE: Record<string, string> = {
  GET: "text-success",
  DELETE: "text-danger",
};

export function OperationPicker({ reading, picked, onPicked }: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const q = filter.trim().toLowerCase();
  const shown = reading.operations.filter(
    (op) => !q || op.key.toLowerCase().includes(q) || op.tool.name.toLowerCase().includes(q),
  );
  const sections = new Map<string, Operation[]>();
  for (const op of reading.operations) {
    const key = sectionOf(op);
    sections.set(key, [...(sections.get(key) ?? []), op]);
  }
  const toggle = (key: string, on: boolean) =>
    onPicked(on ? [...picked, key] : picked.filter((k) => k !== key));

  return (
    <div className="flex flex-col gap-1.5">
      <p className="flex items-baseline gap-2 text-xs font-label">
        {t("customTools.import.operationsTitle")}
        <span className="font-normal text-text-muted">
          {t("customTools.import.picked", {
            count: picked.length,
            total: reading.operations.length,
          })}
        </span>
      </p>
      <div className="flex gap-2">
        <Input
          className="flex-1"
          value={filter}
          placeholder={t("customTools.import.filterOps")}
          aria-label={t("customTools.import.filterOps")}
          onChange={(e) => setFilter(e.target.value)}
        />
        <Button variant="outline" onClick={() => onPicked(defaultPicks(reading))}>
          {t("customTools.import.readsOnly")}
        </Button>
      </div>
      <div className="max-h-64 overflow-y-auto rounded-lg border border-border-subtle">
        {[...sections.entries()].map(([section, ops]) => {
          const visible = ops.filter((op) => shown.includes(op));
          if (visible.length === 0) return null;
          const on = ops.filter((op) => picked.includes(op.key)).length;
          return (
            <div key={section}>
              <p className="bg-surface-sunken px-2.5 py-1 text-2xs font-semibold text-text-muted">
                {t("customTools.import.section", { section, count: on, total: ops.length })}
              </p>
              {visible.map((op) => {
                const method = op.tool.method ?? "GET";
                return (
                  <label
                    key={op.key}
                    className="grid cursor-pointer grid-cols-[16px_56px_minmax(0,1fr)_minmax(0,1fr)_96px] items-center gap-2 border-t border-border-subtle px-2.5 py-1 hover:bg-surface-hover"
                  >
                    <Checkbox
                      checked={picked.includes(op.key)}
                      aria-label={op.tool.name}
                      onChange={(e) => toggle(op.key, e.target.checked)}
                    />
                    <span
                      className={cn("font-mono text-xs", METHOD_TONE[method] ?? "text-warning")}
                    >
                      {method}
                    </span>
                    <span className="truncate font-mono text-xs">{op.tool.path}</span>
                    <span className="truncate font-mono text-xs text-text-muted">
                      {op.tool.name}
                    </span>
                    {operationChangesData(op) ? (
                      <Badge variant="warning">{t("customTools.tools.changesData")}</Badge>
                    ) : (
                      <span />
                    )}
                  </label>
                );
              })}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-text-muted">{t("customTools.import.pickNote")}</p>
      {reading.warnings.map((warning) => (
        <p key={warning} className="text-xs text-warning">
          {warning}
        </p>
      ))}
    </div>
  );
}
