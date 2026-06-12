// components/chat/NewConversationDialog.tsx
// New-conversation dialog: pick an agent, then fill that agent's configuration.
// The configuration area is rendered per agent_key — the built-in agent's area
// is the model selection. Adding another agent type adds a branch to the
// per-agent config block below (and to handleCreate), not a dialog rewrite.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import type { AgentInfo, ConversationCreate } from "@/lib/api/chat";
import type { Model } from "@/lib/api/models";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: AgentInfo[];
  models: Model[];
  onCreate: (body: ConversationCreate) => void;
}

export function NewConversationDialog({
  open,
  onOpenChange,
  agents,
  models,
  onCreate,
}: Props) {
  const { t } = useTranslation();
  const [agentKey, setAgentKey] = useState("builtin");
  const [modelId, setModelId] = useState("");
  // Seed each selection from defaults once per open session — independently,
  // because agents and models are separate queries that can resolve in any
  // order (seeding both on agents' arrival would lock modelId to "" when
  // models are still loading). A background refetch while the dialog is open
  // must not clobber the user's in-progress choices.
  const seededAgentRef = useRef(false);
  const seededModelRef = useRef(false);

  useEffect(() => {
    if (!open) {
      seededAgentRef.current = false;
      seededModelRef.current = false;
      return;
    }
    if (!seededAgentRef.current && agents.length > 0) {
      seededAgentRef.current = true;
      const firstAgent = agents.find((a) => a.available) ?? agents[0];
      setAgentKey(firstAgent?.agent_key ?? "builtin");
    }
    if (!seededModelRef.current && models.length > 0) {
      seededModelRef.current = true;
      setModelId(models.find((m) => m.is_default)?.id ?? models[0]?.id ?? "");
    }
  }, [open, agents, models]);

  const handleCreate = () => {
    const body: ConversationCreate = { agent_key: agentKey };
    if (agentKey === "builtin") {
      body.agent_config = modelId ? { model_id: modelId } : {};
    }
    onCreate(body);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("chat.newConversation.title")}</DialogTitle>
          <DialogDescription>{t("chat.newConversation.agentHint")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{t("chat.newConversation.agent")}</Label>
            <Select value={agentKey} onValueChange={setAgentKey}>
              <SelectTrigger aria-label={t("chat.newConversation.agent")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {agents.map((a) => (
                  <SelectItem key={a.agent_key} value={a.agent_key} disabled={!a.available}>
                    {a.display_name}
                    {a.available ? "" : ` (${t("chat.newConversation.unavailable")})`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Per-agent configuration area, branched by agent_key. */}
          {agentKey === "builtin" && (
            <div className="space-y-1.5">
              <Label>{t("chat.newConversation.model")}</Label>
              {models.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {t("chat.newConversation.noModels")}
                </p>
              ) : (
                <Select value={modelId} onValueChange={setModelId}>
                  <SelectTrigger aria-label={t("chat.newConversation.model")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.display_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={handleCreate}>{t("chat.newConversation.create")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
