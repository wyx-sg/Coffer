// src/components/agents/model/ChangeModelDialog.tsx — the Overview › Model "Change…" flow (boards 2.1.16–2.1.19, 2.1.65).
//
// A 480 form: Provider, Model and Model per tier, as far as the agent and the provider call for them.
// Nothing is written here; Review changes hands the draft to the review (a 1060 preview of
// the files that change) and Apply happens there. The form closes with the
// review once the change is applied.
import { useState } from "react";
import { useTranslation } from "react-i18next";

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
import { useModelSwitchTest } from "@/lib/hooks/useModelSwitchTest";
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
          <DialogTitle>
            {t("agents.changeModel.title", { name: agentTypeLabel(agent.type) })}
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
  const test = useModelSwitchTest(draft.draftConnObj, draft.draftModel);
  const [reviewing, setReviewing] = useState(false);
  if (draft.loading) return <Skeleton className="h-40 w-full" />;
  // A provider must have answered with this model before its change can be
  // reviewed; the built-in login has nothing to test.
  const tested = draft.draftIsBuiltin || test.status.state === "passed";
  const blocked = draft.canReview && !tested;
  return (
    <>
      <div className="flex flex-col gap-4">
        <ModelFormFields agentType={agent.type} draft={draft} onNavigate={onClose} test={test} />
      </div>
      <DialogFooter className="items-center">
        {blocked ? (
          <span id="change-model-blocked" className="mr-auto text-xs text-text-subtle">
            {t(
              test.status.state === "failed"
                ? "agents.changeModel.test.blockedFailed"
                : "agents.changeModel.test.blockedTesting",
            )}
          </span>
        ) : null}
        <Button variant="ghost" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button
          disabled={!draft.canReview || !tested}
          aria-describedby={blocked ? "change-model-blocked" : undefined}
          onClick={() => setReviewing(true)}
        >
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
