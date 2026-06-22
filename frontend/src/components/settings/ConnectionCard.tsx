// components/settings/ConnectionCard.tsx — one LLM-connection row on the
// connections page (spec 011). Shows name + status chips + wire/model/base_url
// and the per-row actions: switch active, edit, delete. The internal-engine
// selection lives in its own section (InternalEngineSettings), not per-card.
// Extracted from LlmConnectionsPage to keep that page within its size budget;
// purely presentational (all mutations are passed in as callbacks).
import { useTranslation } from "react-i18next";
import { Check, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Provider } from "@/lib/api/providers";

interface Props {
  provider: Provider;
  activatePending: boolean;
  deletePending: boolean;
  onActivate: (name: string) => void;
  onEdit: (p: Provider) => void;
  onDelete: (p: Provider) => void;
}

export function ConnectionCard({
  provider: p,
  activatePending,
  deletePending,
  onActivate,
  onEdit,
  onDelete,
}: Props) {
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
          </div>
          <p className="truncate text-xs text-muted-foreground">
            {p.wire_format} · {p.model} · {p.base_url}
          </p>
        </div>
        {/* Ollama is internal-only — never projected to an agent, so it has no
            per-wire "Switch" action. */}
        {p.wire_format !== "ollama" && !p.is_active && (
          <Button
            variant="outline"
            size="sm"
            disabled={activatePending}
            onClick={() => onActivate(p.name)}
          >
            {t("settings.connections.switch")}
          </Button>
        )}
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
