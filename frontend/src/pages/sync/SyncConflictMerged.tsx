// frontend/src/pages/sync/SyncConflictMerged.tsx
//
// A file an agent merged (board 6.4.34): the agent wrote both versions into
// Coffer's marked-up copy, and this card says so, with what that merge changes
// on this Mac underneath. The merge is never an answer by itself — the person
// checks it and marks it resolved, which takes the copy as saved (refused, with
// the line, while a conflict marker is left in it). Back to two choices throws
// the merge away. Open conversation shows only when the daemon knows which
// conversation the agent ran in.
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { ConflictFile } from "@/lib/api/sync";
import { SyncConflictDiff } from "./SyncConflictDiff";
import { clock, otherMachine, refusal } from "./syncConflictFormat";

interface Props {
  file: ConflictFile;
  pending: boolean;
  leaving: boolean;
  error: unknown;
  onResolve: () => void;
  onBack: () => void;
}

export function SyncConflictMerged({ file, pending, leaving, error, onResolve, onBack }: Props) {
  const { t, i18n } = useTranslation();
  const agent = file.agent_name ?? t("sync.resolve.merged.anAgent");
  return (
    <>
      <div
        className="flex items-start gap-3 rounded-xl border border-border bg-surface-raised p-4"
        data-testid="sync-conflict-merged"
      >
        <span className="inline-flex size-[30px] shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
          <MessageSquare className="size-[15px]" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-1.5">
          <p className="text-sm font-semibold text-text">
            {t("sync.resolve.merged.title", {
              agent,
              time: clock(file.agent_merged_at, i18n.language),
            })}
          </p>
          <p className="text-xs text-text-muted">
            {t("sync.resolve.merged.body", { machine: otherMachine(t, file) })}
          </p>
          {error ? (
            <p className="text-xs text-danger" role="alert">
              {refusal(t, error)}
            </p>
          ) : null}
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              loading={pending}
              disabled={leaving}
              onClick={onResolve}
            >
              {t("sync.resolve.editing.markResolved")}
            </Button>
            {file.agent_conversation_id ? (
              <Button asChild size="sm" variant="ghost">
                <Link to={`/conversations/${encodeURIComponent(file.agent_conversation_id)}`}>
                  {t("sync.resolve.merged.openConversation")}
                </Link>
              </Button>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              loading={leaving}
              disabled={pending}
              onClick={onBack}
            >
              {t("sync.resolve.editing.back")}
            </Button>
          </div>
        </div>
      </div>
      <SyncConflictDiff path={file.path} which="merged" />
    </>
  );
}
