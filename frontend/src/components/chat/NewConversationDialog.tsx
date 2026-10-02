// src/components/chat/NewConversationDialog.tsx — New conversation: which agent,
// and the folder it works in; Start opens the draft (spec chat "Create the
// conversation on the first send" — nothing is created until the first message).
// Model and effort are not asked here: they start from the agent's own Model
// tab and switch in the conversation's header. An agent that cannot run a turn
// on this machine is listed but cannot be chosen. The folder is optional — left
// blank, the turn runs in Coffer's own workspace — and opens on the last one used.
// With no agent that can run, it says how to get one (NoManagedAgentHelp).
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { FolderPickerField } from "@/components/FolderPickerField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import { readLastWorkingDir } from "@/lib/conversations/lastWorkingDir";
import { NoManagedAgentHelp } from "./NoManagedAgentHelp";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: AgentProviderInfo[];
  onStart: (config: { agentKey: string; cwd: string | null }) => void;
}

export function NewConversationDialog({ open, onOpenChange, agents, onStart }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const firstAvailable = agents.find((a) => a.available)?.agent_key ?? "";
  const [agentKey, setAgentKey] = useState(firstAvailable);
  const [cwd, setCwd] = useState<string | null>(null);

  // Each opening starts from the first agent that can run and the last folder.
  useEffect(() => {
    if (!open) return;
    setAgentKey(firstAvailable);
    setCwd(readLastWorkingDir());
  }, [open, firstAvailable]);

  const start = () => {
    if (!agentKey) return;
    onStart({ agentKey, cwd: cwd?.trim() || null });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("conversations.new.title")}</DialogTitle>
          <DialogDescription>{t("conversations.new.hint")}</DialogDescription>
        </DialogHeader>
        {agents.length === 0 || !firstAvailable ? (
          <NoManagedAgentHelp layout="inline" />
        ) : (
          <form
            id={`${id}-form`}
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              start();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor={`${id}-agent`}>{t("conversations.new.agent")}</Label>
              <Select value={agentKey} onValueChange={setAgentKey}>
                <SelectTrigger id={`${id}-agent`} aria-label={t("conversations.new.agent")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {agents
                    .filter((a) => a.available)
                    .map((a) => (
                      <SelectItem key={a.agent_key} value={a.agent_key}>
                        <span className="inline-flex items-center gap-2">
                          <AgentBadge type={a.agent_key} size="sm" tooltip={false} />
                          {a.display_name}
                        </span>
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${id}-cwd`}>{t("conversations.new.workingDir")}</Label>
              <FolderPickerField
                inputId={`${id}-cwd`}
                ariaLabel={t("conversations.new.workingDir")}
                value={cwd}
                onChange={setCwd}
                placeholder={t("conversations.new.workingDirPlaceholder")}
                clearable
                typeable
              />
            </div>
          </form>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form={`${id}-form`} disabled={!agentKey || !firstAvailable}>
            {t("conversations.new.start")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
