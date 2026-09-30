// src/components/custom-tools/ToolReachField.tsx — one tool's Available to in its drawer: follow the
// group (Group default) or its own agents (Only for this tool), with what the group gives beside it.
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import { Segmented } from "@/components/ui/segmented";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { useAgents } from "@/lib/hooks/useAgents";
import { DraftReachField } from "./DraftReachField";

interface Props {
  group: CustomToolGroup;
  /** The override: agent uids, or `null` to follow the group. */
  value: string[] | null;
  onChange: (value: string[] | null) => void;
}

type Mode = "group" | "tool";

export function ToolReachField({ group, value, onChange }: Props) {
  const { t } = useTranslation();
  const { data: agents } = useAgents();
  const total = agents?.length ?? 0;
  const groupCount = group.scope === null ? total : group.scope.length;
  const mode: Mode = value === null ? "group" : "tool";
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("customTools.fields.availableTo")}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented<Mode>
          label={t("customTools.fields.availableTo")}
          value={mode}
          options={[
            { value: "group", label: t("customTools.tools.groupDefault") },
            { value: "tool", label: t("customTools.editor.onlyThisTool") },
          ]}
          // Narrowing starts from what the group gives, so it is one untick away.
          onChange={(next) =>
            onChange(next === "group" ? null : (group.scope ?? (agents ?? []).map((a) => a.uid)))
          }
        />
        {value !== null ? <DraftReachField value={value} onChange={onChange} pickOnly /> : null}
      </div>
      <p className="text-xs text-text-muted">
        {t(
          `customTools.editor.${value === null ? "reachFollows" : "reachOverrides"}${group.scope === null ? "All" : ""}`,
          { count: groupCount, total },
        )}
      </p>
    </div>
  );
}
