// src/components/conversations/NewConversationDialog.tsx — spec chat "Start a new
// conversation in the terminal". Two fields: the agent (preset to the one chosen
// last, or the caller's) and the working directory (Coffer's workspace unless
// another folder is picked). Confirm is a split button named for the preferred
// terminal; it asks the daemon for a blank session and closes once the daemon
// has started it. A refusal shows its reason here and the dialog stays open.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SplitButton } from "@/components/ui/split-button";
import { useToast } from "@/components/ui/toast";
import { agentDisplayName } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { fsApi } from "@/lib/api/fs";
import { useTerminalChoices } from "@/lib/hooks/useTerminals";
import { getPreferredTerminal } from "@/lib/preferences";

const LAST_AGENT_KEY = "coffer.newConversationAgent";

function readLastAgent(): string | null {
  try {
    return localStorage.getItem(LAST_AGENT_KEY);
  } catch {
    return null;
  }
}

function writeLastAgent(key: string): void {
  try {
    localStorage.setItem(LAST_AGENT_KEY, key);
  } catch {
    // Not remembered; the choice lasts until the page reloads.
  }
}

/** The agent the dialog opens with: the caller's, else the last chosen, else the first. */
function initialAgent(agents: readonly AgentOut[], preset?: string): string {
  const has = (key: string | null | undefined) => !!key && agents.some((a) => a.type === key);
  if (has(preset)) return preset as string;
  const last = readLastAgent();
  if (has(last)) return last as string;
  return agents[0]?.type ?? "";
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: readonly AgentOut[];
  /** Preselects this agent (an agent's Sessions tab). */
  agentKey?: string;
}

export function NewConversationDialog({ open, onOpenChange, agents, agentKey }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const terminals = useTerminalChoices();
  const [agent, setAgent] = useState("");
  // null: Coffer's workspace — the daemon starts there when no directory is sent.
  const [cwd, setCwd] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAgent(initialAgent(agents, agentKey));
    setCwd(null);
    setError(null);
  }, [open, agents, agentKey]);

  const start = async (chosen?: string, label = terminals.label) => {
    if (!agent || pending) return;
    setPending(true);
    setError(null);
    try {
      await fsApi.openTerminal({
        agent,
        cwd: cwd?.trim() || null,
        terminal: (chosen ?? getPreferredTerminal()) || null,
      });
    } catch (e) {
      setError(translateApiError(t, e));
      setPending(false);
      return;
    }
    writeLastAgent(agent);
    toast.success(t("terminal.opened", { terminal: label }));
    setPending(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("newConversation.title")}</DialogTitle>
          <DialogDescription>{t("newConversation.description")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-label text-text">{t("newConversation.agent")}</span>
            <Select value={agent} onValueChange={setAgent}>
              <SelectTrigger aria-label={t("newConversation.agent")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {agents.map((a) => (
                  <SelectItem key={a.uid} value={a.type}>
                    {agentDisplayName(a)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="new-conversation-dir" className="text-xs font-label text-text">
              {t("newConversation.directory")}
            </label>
            <FolderPickerField
              inputId="new-conversation-dir"
              value={cwd}
              onChange={setCwd}
              placeholder={t("newConversation.workspacePlaceholder")}
              typeable
            />
            <p className="text-xs text-text-muted">{t("newConversation.directoryHint")}</p>
          </div>
          {error ? (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
            {t("common.cancel")}
          </Button>
          <SplitButton
            label={t("newConversation.openIn", { terminal: terminals.label })}
            onClick={() => void start()}
            menuLabel={t("newConversation.moreTerminals")}
            disabled={!agent || pending}
            actions={terminals.others.map((o) => ({
              key: o.value || "system",
              label: t("newConversation.openIn", { terminal: o.label }),
              onSelect: () => void start(o.value, o.label),
            }))}
          />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
