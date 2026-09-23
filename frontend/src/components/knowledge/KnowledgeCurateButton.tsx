// frontend/src/components/knowledge/KnowledgeCurateButton.tsx
//
// The manual curation trigger on a collection's page (spec knowledge "Present a
// collection as one tree in the web UI"):
// one bounded pass that merges the next pending item — new material from the
// inbox, or a document edited since curation last saw it — into the
// collection's documents. The background sweep runs the same pass on an
// interval; this is the "do it now" for something somebody has just added.
//
// Whether a pass is running is the DAEMON's answer, not this component's:
// leaving the page mid-pass and coming back must still show the pass, not an
// idle button inviting a second concurrent rewrite of the same files. The
// mutation's own pending state covers the moment between the click and the
// first poll.
//
// The 409 is the point of this file. The daemon refuses a second pass rather
// than queueing it, and a button that merely goes dead says nothing about why
// — so a refusal is turned into the button's own label and tooltip ("a pass is
// already running"), which is also what the next poll will independently say.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { useCurateCollection } from "@/lib/hooks/useKnowledge";
import { useUpkeepRunning } from "@/lib/hooks/useUpkeep";

export function KnowledgeCurateButton({
  collectionUid,
  collectionName,
}: {
  /** The collection to curate — what the request is addressed to. */
  collectionUid: string;
  /** Its label, which is also its directory name, and therefore what
   *  `/upkeep/runs` names a running pass by. */
  collectionName: string;
}) {
  const { t } = useTranslation();
  const curate = useCurateCollection(collectionUid);
  const refusedAsRunning =
    curate.error instanceof ApiError && curate.error.code === "UPKEEP_ALREADY_RUNNING";
  // Three sources, one answer: the daemon's run list, this click's own refusal,
  // and the optimistic gap between the click and the first poll.
  const alreadyRunning = useUpkeepRunning("knowledge", collectionName) || refusedAsRunning;
  const busy = alreadyRunning || curate.isPending;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => curate.mutate(null)}
          disabled={busy}
        >
          <RefreshCw className={busy ? "mr-1.5 size-3.5 animate-spin" : "mr-1.5 size-3.5"} />
          {alreadyRunning ? t("knowledge.detail.curateRunning") : t("knowledge.detail.curate")}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {alreadyRunning ? t("knowledge.detail.curateRunning") : t("knowledge.detail.curateHint")}
      </TooltipContent>
    </Tooltip>
  );
}
