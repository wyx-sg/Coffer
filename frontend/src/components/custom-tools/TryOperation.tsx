// src/components/custom-tools/TryOperation.tsx — Import step 1's Try an operation: run one picked operation
// against the spec's base URL before the group exists (no secret is sent; nothing is saved).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { OpenApiReading } from "@/lib/api/customTools";
import { argsFromSchema } from "@/lib/customTools/schemaArgs";
import type { GroupDraft } from "./addFlow";
import { ToolTestSection } from "./ToolTestSection";

interface Props {
  reading: OpenApiReading;
  group: GroupDraft;
  picked: string[];
}

export function TryOperation({ reading, group, picked }: Props) {
  const { t } = useTranslation();
  const choices = reading.operations.filter((op) => picked.includes(op.key));
  const [key, setKey] = useState(choices[0]?.key ?? "");
  const op = choices.find((o) => o.key === key) ?? choices[0];
  if (!op) return <p className="text-xs text-text-muted">{t("customTools.import.tryNone")}</p>;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border-subtle p-3">
      <Select value={op.key} onValueChange={setKey}>
        <SelectTrigger className="font-mono" aria-label={t("customTools.import.tryPick")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {choices.map((o) => (
            <SelectItem key={o.key} value={o.key} className="font-mono">
              {o.tool.name} · {o.key}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <ToolTestSection
        key={op.key}
        target={{ unsaved: { name: group.name, base_url: group.baseUrl.trim(), headers: {} } }}
        secret={null}
        timeoutSeconds={30}
        args={argsFromSchema(op.tool.input_schema ?? {})}
        draft={() => ({ ...op.tool, name: op.tool.name })}
        ready={group.baseUrl.trim() !== ""}
        saveWord="add"
      />
    </div>
  );
}
