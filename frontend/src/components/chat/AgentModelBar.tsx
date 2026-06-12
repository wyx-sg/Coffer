// components/chat/AgentModelBar.tsx
// Top bar in the message thread: agent selector (v1: single "Coffer Assistant")
// and a model selector for the current conversation.
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Model } from "@/lib/api/models";
import type { Conversation } from "@/lib/api/chat";

interface Props {
  conversation: Conversation;
  models: Model[];
  onModelChange: (modelId: string | null) => void;
  /** Display name of the conversation's agent, from the agents API. */
  agentLabel?: string;
  /** Whether to show the per-conversation model selector (a built-in-agent
   *  control; other agents carry no Coffer-registered model). */
  showModelSelector?: boolean;
}

export function AgentModelBar({
  conversation,
  models,
  onModelChange,
  agentLabel,
  showModelSelector = true,
}: Props) {
  const { t } = useTranslation();
  // When the conversation has no model override, fall back to the default model
  // so the selector shows the model that is actually in use rather than a blank.
  const defaultModelId = models.find((m) => m.is_default)?.id ?? "";
  const currentModelId = conversation.model_id ?? defaultModelId;

  return (
    <div className="flex items-center gap-3 border-b border-border bg-card/50 px-4 py-2">
      {/* Agent label — sourced from the registry via the agents API, so a
          second agent shows its own name rather than the built-in one. */}
      <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Bot className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
        <span>{agentLabel ?? t("chat.agent.cofferAssistant")}</span>
      </div>

      {showModelSelector && (
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {t("chat.modelBar.model")}
          </span>
          <Select
            value={currentModelId}
            onValueChange={(v) => onModelChange(v || null)}
          >
            <SelectTrigger className="h-7 w-44 text-xs" aria-label={t("chat.modelBar.selectAria")}>
              <SelectValue placeholder={t("chat.modelBar.noModel")} />
            </SelectTrigger>
            <SelectContent>
              {models.length === 0 ? (
                <SelectItem value="__none__" disabled>
                  {t("chat.modelBar.noModels")}
                </SelectItem>
              ) : (
                models.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.display_name}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}
