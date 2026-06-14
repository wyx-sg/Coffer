// components/chat/HistorySessionView.tsx
// Read-only browse of one indexed transcript's scrubbed turns (ADR-022).
// No composer, no edit affordances — history is immutable here.
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useHistorySession } from "@/lib/hooks/useHistory";
import type { HistoryHit } from "@/lib/api/history";

interface Props {
  hit: Pick<HistoryHit, "agent_type" | "session_id" | "title" | "project_path">;
  onBack: () => void;
}

export function HistorySessionView({ hit, onBack }: Props) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useHistorySession(hit.agent_type, hit.session_id);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Button
          variant="ghost"
          size="sm"
          className="size-7 shrink-0 p-0"
          onClick={onBack}
          aria-label={t("history.back")}
        >
          <ArrowLeft className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{hit.title}</p>
          <p className="truncate text-xs text-muted-foreground">
            {hit.agent_type}
            {hit.project_path ? ` · ${hit.project_path}` : ""}
          </p>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {isLoading && <p className="text-sm text-muted-foreground">{t("common.loading")}</p>}
        {isError && <p className="text-sm text-destructive">{t("history.loadFailed")}</p>}
        {data?.turns.map((turn, i) => (
          <div key={i} className="space-y-0.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {turn.role}
            </p>
            <p className="whitespace-pre-wrap break-words rounded-md bg-card px-3 py-2 text-sm text-foreground shadow-sm">
              {turn.text}
            </p>
          </div>
        ))}
        {data && data.turns.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("history.emptySession")}</p>
        )}
      </div>
    </div>
  );
}
