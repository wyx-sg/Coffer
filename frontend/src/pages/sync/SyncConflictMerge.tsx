// frontend/src/pages/sync/SyncConflictMerge.tsx
//
// "Merge with an agent", under the two choices of a file an agent may merge
// (spec vault-sync "Hand a conflict's merge to an agent"). Merging two edits
// is judgement, so it is handed to the person's agent with the backend's
// prompt, which names every marked-up copy — the agent edits those copies
// only, never the vault or git, and Coffer commits the result. "I merged it"
// then records the saved copy of every such file as its answer
// (`POST /sync/stop/merged`); while any copy still has a conflict marker the
// whole request is refused, and the refusal (naming the file and line) shows
// here. Deliberately quieter than the two choices it sits under.
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import { useMarkMerged } from "@/lib/hooks/useSyncStop";
import { refusal } from "./syncConflictFormat";

export function SyncConflictMerge({ prompt }: { prompt: string }) {
  const { t } = useTranslation();
  const merged = useMarkMerged();

  return (
    <section
      className="flex flex-col gap-2 rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2.5"
      aria-labelledby="sync-conflict-merge-title"
      data-testid="sync-conflict-merge"
    >
      <div className="flex flex-col gap-0.5">
        <h3 id="sync-conflict-merge-title" className="text-xs font-label text-text">
          {t("sync.resolve.merge.title")}
        </h3>
        <p className="text-xs text-text-muted">{t("sync.resolve.merge.body")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <AgentHandoff prompt={prompt} size="sm" />
        <Button
          type="button"
          variant="outline"
          size="sm"
          loading={merged.isPending}
          onClick={() => merged.mutate()}
        >
          <Check aria-hidden />
          {t("sync.resolve.merge.done")}
        </Button>
      </div>
      {merged.error ? (
        <p className="text-xs text-danger" role="alert">
          {refusal(t, merged.error)}
        </p>
      ) : null}
    </section>
  );
}
