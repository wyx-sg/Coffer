// frontend/src/pages/sync/SyncResolveConflictsPage.tsx
//
// Resolve conflicts (`/sync/conflicts`, boards 6.5.06 / 6.5.07 / 6.5.24): the
// round stopped on files both Macs changed, with nothing checked out and
// nothing pushed. The files on the left, each with its answer; the chosen
// file on the right with its two choices, the editor, and — for a file an
// agent may merge — the hand-off. Answers are recorded as they are picked but
// nothing is written into the vault until Continue round, which is offered
// once every file has one. Leave for later keeps the round stopped.
//
// Which file is open lives in the URL (`?path=`), so the Status card's rows
// open the page at their file. Whether a file is open in the editor is this
// page's own state: the marked-up copy exists from the moment the round
// stops (the agent hand-off names it), so the copy alone does not mean the
// person chose to edit it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/status/StatusPill";
import { useSyncStop } from "@/lib/hooks/useSyncStop";
import { SyncConflictFileList } from "./SyncConflictFileList";
import { SyncConflictFooter } from "./SyncConflictFooter";
import { SyncConflictPane } from "./SyncConflictPane";
import { clock } from "./syncConflictFormat";

export function SyncResolveConflictsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState<ReadonlySet<string>>(new Set());
  const { data, isLoading } = useSyncStop(true);
  const round = data?.stopped && data.round?.kind === "conflicts" ? data.round : null;

  const header = (
    <PageHeader
      title={t("sync.resolve.title")}
      badges={round ? <StatusPill tone="err">{t("sync.resolve.pill")}</StatusPill> : null}
      subtitle={
        round
          ? t("sync.resolve.subline", {
              time: clock(round.raised_at, i18n.language),
              machine:
                round.files.find((f) => f.theirs_machine)?.theirs_machine ??
                t("sync.conflicts.otherMachine"),
            })
          : undefined
      }
    />
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        {header}
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }
  if (!round || round.files.length === 0) {
    return (
      <div className="space-y-6">
        {header}
        <EmptyState
          title={t("sync.resolve.empty.title")}
          description={t("sync.resolve.empty.body")}
        />
      </div>
    );
  }

  const wanted = params.get("path");
  const file =
    round.files.find((f) => f.path === wanted) ??
    round.files.find((f) => f.answer === null) ??
    round.files[0]!;
  const setEditingFor = (path: string, on: boolean) =>
    setEditing((prev) => {
      const next = new Set(prev);
      if (on) next.add(path);
      else next.delete(path);
      return next;
    });

  return (
    <div className="space-y-6">
      {header}
      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
        <div className="flex min-h-[420px]">
          <SyncConflictFileList
            files={round.files}
            selected={file.path}
            editing={editing}
            onSelect={(path) => setParams({ path }, { replace: true })}
          />
          <SyncConflictPane
            key={file.path}
            file={file}
            handoff={round.handoff?.prompt ?? null}
            editing={editing.has(file.path) && file.answer === null && !file.secret}
            onEditing={(on) => setEditingFor(file.path, on)}
          />
        </div>
        <SyncConflictFooter round={round} onDone={() => navigate("/sync")} />
      </div>
    </div>
  );
}
