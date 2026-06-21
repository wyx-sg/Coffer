// frontend/src/components/agents/AgentConversationsDistillCell.tsx
// Per-row "Distill to memory" action for the conversations tab: triggers
// distillation of one transcript session and renders the returned insights
// inline below the button.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { InsightOut, TranscriptSessionSummary } from "@/lib/api/agentChat";
import { useDistillTranscript } from "@/lib/hooks/useAgentChatHistory";

interface Props {
  session: TranscriptSessionSummary;
  name: string;
}

export function DistillCell({ session, name }: Props) {
  const { t } = useTranslation();
  const [insights, setInsights] = useState<InsightOut[]>([]);
  const [entryCount, setEntryCount] = useState<number | null>(null);
  const distill = useDistillTranscript(name);

  const handleDistill = () => {
    distill.mutate(
      { session_id: session.session_id },
      {
        onSuccess: (result) => {
          setInsights(result.insights);
          setEntryCount(result.journal_entries.length);
        },
      },
    );
  };

  return (
    <div className="space-y-2">
      <Button
        size="sm"
        variant="outline"
        disabled={distill.isPending}
        onClick={(e) => {
          e.stopPropagation();
          handleDistill();
        }}
        aria-label={t("agents.conversationsTab.distillAria", { session: session.session_id })}
      >
        {distill.isPending
          ? t("agents.conversationsTab.distilling")
          : t("agents.conversationsTab.distill")}
      </Button>

      {entryCount !== null && insights.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("agents.conversationsTab.noInsights")}</p>
      ) : null}

      {entryCount !== null && insights.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("agents.conversationsTab.distilledCount", { count: insights.length })}
        </p>
      ) : null}

      {insights.length > 0 ? (
        <div className="space-y-2 pt-1">
          {insights.map((insight, index) => (
            <div
              key={`${index}-${insight.name}`}
              className="space-y-1 rounded-md border bg-card px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium">{insight.name}</span>
              </div>
              {insight.description ? (
                <p className="text-xs text-muted-foreground">{insight.description}</p>
              ) : null}
              <p className="text-xs">{insight.body}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
