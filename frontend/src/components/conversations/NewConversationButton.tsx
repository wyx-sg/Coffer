// src/components/conversations/NewConversationButton.tsx — spec chat "Start a new
// conversation in the terminal": the header action of the Conversations page and
// of an agent's Sessions tab. Disabled, with the reason on hover, while no agent
// is managed.
import { SquarePen } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAgents } from "@/lib/hooks/useAgents";
import { NewConversationDialog } from "./NewConversationDialog";

export function NewConversationButton({ agentKey }: { agentKey?: string }) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const [open, setOpen] = useState(false);
  const none = agents.length === 0;
  const button = (
    <Button type="button" disabled={none} onClick={() => setOpen(true)}>
      <SquarePen aria-hidden />
      {t("newConversation.button")}
    </Button>
  );
  return (
    <>
      {none ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex" tabIndex={0}>
                {button}
              </span>
            </TooltipTrigger>
            <TooltipContent>{t("newConversation.noAgent")}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        button
      )}
      <NewConversationDialog
        open={open}
        onOpenChange={setOpen}
        agents={agents}
        agentKey={agentKey}
      />
    </>
  );
}
