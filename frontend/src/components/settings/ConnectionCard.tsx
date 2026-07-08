// components/settings/ConnectionCard.tsx — one LLM-connection row on the
// connections page (spec 011). Shows name + active chip + wire/base_url and the
// connection's compatible agents, plus the per-row edit / delete actions. There
// is NO per-row "switch" — activation is per-agent and lives on the Agent detail
// → Overview tab; this page is purely the connection library. The internal-engine
// selection lives in its own section (InternalEngineSettings). Purely
// presentational (all mutations are passed in as callbacks).
import { useTranslation } from "react-i18next";
import { Check, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { AgentType, Provider } from "@/lib/api/providers";

interface Props {
  provider: Provider;
  deletePending: boolean;
  onEdit: (p: Provider) => void;
  onDelete: (p: Provider) => void;
}

const AGENT_LABEL_KEY: Record<AgentType, string> = {
  claude_code: "settings.connections.agentClaudeCode",
  codex: "settings.connections.agentCodex",
  opencode: "settings.connections.agentOpencode",
  hermes: "settings.connections.agentHermes",
  cursor: "settings.connections.agentCursor",
};

export function ConnectionCard({ provider: p, deletePending, onEdit, onDelete }: Props) {
  const { t } = useTranslation();
  return (
    <Card className="paper-card">
      <CardContent className="flex items-center gap-3 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium">{p.name}</span>
            {p.is_active && (
              <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                <Check className="size-3" />
                {t("settings.connections.active")}
              </span>
            )}
            {/* Which agents this connection projects into (the compatible set). */}
            {(p.compatible_agents ?? []).map((a) => (
              <span
                key={a}
                className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                {t(AGENT_LABEL_KEY[a])}
              </span>
            ))}
          </div>
          <p className="truncate text-xs text-muted-foreground">
            {p.protocol} · {p.base_url}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="size-7 p-0 hover:text-primary"
          onClick={() => onEdit(p)}
          aria-label={t("common.edit")}
        >
          <Pencil className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="size-7 p-0 hover:text-destructive"
          onClick={() => onDelete(p)}
          disabled={deletePending}
          aria-label={t("common.delete")}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </CardContent>
    </Card>
  );
}
