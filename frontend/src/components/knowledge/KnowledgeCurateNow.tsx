// frontend/src/components/knowledge/KnowledgeCurateNow.tsx
//
// The one manual curation trigger — a quiet button in the Inbox view (Recent
// changes' waiting list has its own, curating every collection),
// nowhere else (spec knowledge "Present a collection as one
// tree in the web UI"). It runs passes one at a time until nothing is pending
// ("Run curation on a sweep and on demand"); while it runs it reads
// "Curating · n of m" from the daemon's in-flight list, so leaving mid-run and
// coming back still shows the run rather than an idle button inviting a second
// one. A pass already in flight — refused 409 — says so on the button; a
// finished run leaves one summary toast, a failed one an error toast with an
// Activity action.
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { useCurateCollection } from "@/lib/hooks/useKnowledge";
import { useUpkeepRun } from "@/lib/hooks/useUpkeep";
import { curatingLabel } from "@/lib/knowledge/text";

interface Props {
  /** The collection to curate, by uid — what the route and the run list key on. */
  collectionUid: string;
  /** Ghost by default; the Inbox view asks for the small secondary button. */
  variant?: "ghost" | "outline";
  /** Whether the sparkle shows before the label (default); off for a plain label. */
  icon?: boolean;
}

export function KnowledgeCurateNow({ collectionUid, variant = "ghost", icon = true }: Props) {
  const { t } = useTranslation();
  const curate = useCurateCollection(collectionUid);
  const run = useUpkeepRun("knowledge", collectionUid);
  const refused =
    curate.error instanceof ApiError && curate.error.code === "UPKEEP_ALREADY_RUNNING";
  const busy = run !== null || curate.isPending;

  return (
    <Button
      type="button"
      variant={variant}
      size="sm"
      onClick={() => curate.mutate(null)}
      disabled={busy}
    >
      {icon ? <Sparkles aria-hidden /> : null}
      {busy
        ? curatingLabel(t, run)
        : refused
          ? t("knowledge.curate.alreadyRunning")
          : t("knowledge.curate.now")}
    </Button>
  );
}
