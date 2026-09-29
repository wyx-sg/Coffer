// src/components/change-preview/WhatWillHappen.tsx
// The sunken "What will happen" well: one plain sentence per agent, led by its badge and name.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { agentTypeLabel } from "@/lib/agents/display";
import type { ChangeSummaryLine } from "./changeCounts";

interface Props {
  summaries: readonly ChangeSummaryLine[];
}

export function WhatWillHappen({ summaries }: Props) {
  const { t } = useTranslation();
  if (summaries.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-surface-sunken p-3">
      <span className="text-2xs font-semibold uppercase tracking-[.04em] text-text-subtle">
        {t("changePreview.whatWillHappen")}
      </span>
      {summaries.map((line, index) => (
        <p key={`${line.agentType}-${line.agentName ?? ""}-${index}`} className="flex gap-2">
          <AgentBadge type={line.agentType} name={line.agentName} size="sm" />
          <span className="min-w-0 text-xs leading-[1.45] text-text-muted">
            <span className="font-label text-text">
              {line.agentName ?? agentTypeLabel(line.agentType)}.
            </span>{" "}
            {line.text}
          </span>
        </p>
      ))}
    </div>
  );
}
