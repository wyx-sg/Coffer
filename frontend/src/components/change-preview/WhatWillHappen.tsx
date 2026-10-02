// src/components/change-preview/WhatWillHappen.tsx
// The "What will happen" block: one plain sentence per agent, led by its badge and name.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { agentTypeLabel } from "@/lib/agents/display";
import type { ChangeSummaryLine } from "@/lib/changePreview/changeCounts";

interface Props {
  summaries: readonly ChangeSummaryLine[];
}

export function WhatWillHappen({ summaries }: Props) {
  const { t } = useTranslation();
  if (summaries.length === 0) return null;
  return (
    <Section title={t("changePreview.whatWillHappen")} gap="snug">
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
    </Section>
  );
}
