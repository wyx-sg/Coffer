// frontend/src/pages/sync/SyncConflictCopyCard.tsx
//
// A file whose marked-up copy is being worked on outside Coffer (spec
// vault-sync "Show a conflict as a banner"): open in the person's editor, or
// merged there by an agent. Coffer shows none of the copy's text and no diff of
// the merge — the editor is where it is read. Mark resolved answers `edited`
// from the copy as saved and is refused, with the line, while a conflict marker
// is left in it; Back to two choices forgets the copy, the hand-off and any
// answer for good.
import { AlertTriangle, ExternalLink, MessageSquare, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { ConflictFile } from "@/lib/api/sync";
import { clock, refusal } from "./syncConflictFormat";

interface Props {
  file: ConflictFile;
  /** `editing`: opened in the editor; `merged`: an agent wrote the merge. */
  state: "editing" | "merged";
  /** Mark resolved is in flight. */
  pending: boolean;
  /** Open in editor or Back to two choices is in flight. */
  busy: boolean;
  error: unknown;
  onOpen: () => void;
  onResolve: () => void;
  onBack: () => void;
}

export function SyncConflictCopyCard(props: Props) {
  const { file, state, pending, busy, error, onOpen, onResolve, onBack } = props;
  const { t, i18n } = useTranslation();
  const merged = state === "merged";
  const Icon = merged ? MessageSquare : Pencil;
  return (
    <div
      className="flex items-start gap-3 rounded-xl border border-border bg-surface-raised p-4"
      data-testid={merged ? "sync-conflict-merged" : "sync-conflict-editing"}
    >
      <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-warning-soft text-warning">
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className="flex min-w-0 flex-col gap-1.5">
        <p className="text-sm font-label text-text">
          {merged
            ? t("sync.resolve.copy.mergedTitle", {
                agent: file.agent_name ?? t("sync.resolve.copy.anAgent"),
                time: clock(file.agent_merged_at, i18n.language),
              })
            : t("sync.resolve.copy.editingTitle")}
        </p>
        <p className="text-xs text-text-muted">
          {merged ? t("sync.resolve.copy.mergedBody") : t("sync.resolve.copy.editingBody")}
        </p>
        {error ? (
          <p className="flex items-start gap-1.5 text-xs text-danger" role="alert">
            <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
            {refusal(t, error)}
          </p>
        ) : null}
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pending || busy}
            onClick={onOpen}
          >
            <ExternalLink aria-hidden />
            {t("sync.resolve.openEditor")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            loading={pending}
            disabled={busy}
            onClick={onResolve}
          >
            {t("sync.resolve.copy.markResolved")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={pending || busy}
            onClick={onBack}
          >
            {t("sync.resolve.copy.back")}
          </Button>
        </div>
      </div>
    </div>
  );
}
