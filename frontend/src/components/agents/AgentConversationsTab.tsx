// frontend/src/components/agents/AgentConversationsTab.tsx
// "Conversations" tab on the agent detail page: lists local transcript sessions
// and lets the user distill them into Coffer memory facts via a per-row action.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { InsightOut, TranscriptSessionSummary } from "@/lib/api/agentChat";
import { useAgentTranscripts, useDistillTranscript } from "@/lib/hooks/useAgentChatHistory";

// ---------------------------------------------------------------------------
// Sub-component: the distill button + inline insight viewer for a single row
// ---------------------------------------------------------------------------

interface DistillCellProps {
  session: TranscriptSessionSummary;
  name: string;
}

function DistillCell({ session, name }: DistillCellProps) {
  const { t } = useTranslation();
  const [insights, setInsights] = useState<InsightOut[]>([]);
  const [factCount, setFactCount] = useState<number | null>(null);
  const distill = useDistillTranscript(name);

  const handleDistill = () => {
    distill.mutate(
      { session_id: session.session_id },
      {
        onSuccess: (result) => {
          setInsights(result.insights);
          setFactCount(result.fact_ids.length);
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
        aria-label={t("agents.conversationsTab.distillAria", {
          session: session.session_id,
        })}
      >
        {distill.isPending
          ? t("agents.conversationsTab.distilling")
          : t("agents.conversationsTab.distill")}
      </Button>

      {factCount !== null && insights.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("agents.conversationsTab.noInsights")}
        </p>
      ) : null}

      {factCount !== null && insights.length > 0 ? (
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
                <Badge variant="secondary">{insight.type}</Badge>
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

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  /** Agent name — used as the route param for transcript queries. */
  name: string;
}

export function AgentConversationsTab({ name }: Props) {
  const { t } = useTranslation();
  const { data, isPending, error } = useAgentTranscripts(name);

  const rows = data?.sessions ?? [];

  const columns: Column<TranscriptSessionSummary>[] = [
    {
      key: "project_path",
      header: t("agents.conversationsTab.colProject"),
      cell: (s) => (
        <span className="break-all font-mono text-xs">
          {s.project_path ?? <span className="text-muted-foreground">—</span>}
        </span>
      ),
    },
    {
      key: "message_count",
      header: t("agents.conversationsTab.colMessages"),
      className: "whitespace-nowrap text-right",
      cell: (s) => <span className="text-sm tabular-nums">{s.message_count}</span>,
    },
    {
      key: "started_at",
      header: t("agents.conversationsTab.colStarted"),
      className: "whitespace-nowrap",
      cell: (s) =>
        s.started_at ? (
          <span className="text-xs text-muted-foreground">
            {new Date(s.started_at).toLocaleString()}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        ),
    },
    {
      key: "action",
      header: "",
      className: "text-right",
      cell: (s) => <DistillCell session={s} name={name} />,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">
          {t("agents.conversationsTab.title")}
        </h3>
        <p className="text-xs text-muted-foreground">{t("agents.conversationsTab.subtitle")}</p>
      </div>

      {isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : error ? (
        <p className="text-sm text-destructive">{translateApiError(t, error)}</p>
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(s) => s.session_id}
          emptyMessage={t("agents.conversationsTab.empty")}
        />
      )}
    </div>
  );
}
