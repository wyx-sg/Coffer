// src/components/agents/model/ChangeModelDialog.tsx — the Overview › Model "Change…" flow (boards 2.1.16–2.1.19, 2.1.65).
//
// A 480 form (Experimental tag): Provider, Model, Effort and Model per tier, as far as the agent and the provider call for them.
// Nothing is written here; Review changes hands the draft to the review (a 1060 preview of
// the files that change) and Apply happens there. The form closes with the
// review once the change is applied.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ExperimentalTag } from "@/components/ExperimentalTag";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";
import { ChangeModelReview } from "./ChangeModelReview";
import { ModelFormFields } from "./ModelFormFields";

interface Props {
  agent: AgentOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChangeModelDialog({ agent, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {t("agents.changeModel.title", { name: agentTypeLabel(agent.type) })}
            <ExperimentalTag />
          </DialogTitle>
          <DialogDescription className="text-sm">
            {t("agents.changeModel.description")}
          </DialogDescription>
        </DialogHeader>
        <Form agent={agent} onClose={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

/** Mounted with the dialog, so the draft starts from what is applied each time. */
function Form({ agent, onClose }: { agent: AgentOut; onClose: () => void }) {
  const { t } = useTranslation();
  const draft = useAgentConnectionDraft(agent);
  const [reviewing, setReviewing] = useState(false);
  if (draft.loading) return <Skeleton className="h-40 w-full" />;
  return (
    <>
      <div className="flex flex-col gap-4">
        <ModelFormFields agentType={agent.type} draft={draft} onNavigate={onClose} />
      </div>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!draft.canReview} onClick={() => setReviewing(true)}>
          {t("agents.changeModel.reviewButton")}
        </Button>
      </DialogFooter>
      <ChangeModelReview
        agent={agent}
        draft={draft}
        open={reviewing}
        onOpenChange={setReviewing}
        onApplied={onClose}
      />
    </>
  );
}
