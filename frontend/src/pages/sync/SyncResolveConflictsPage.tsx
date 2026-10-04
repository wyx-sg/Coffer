// frontend/src/pages/sync/SyncResolveConflictsPage.tsx
//
// Resolve conflicts (`/sync/conflicts`, boards 6.4.06 / 6.4.07 / 6.4.34): the
// round stopped on files both Macs changed, with nothing checked out and
// nothing pushed. The files on the left, each with its answer; the chosen
// file on the right with its two choices, the editor, or an agent's merge to
// check. Answers are recorded as they are picked but nothing is written into
// the vault until Continue round, which is offered once every file has one.
// Leave for later keeps the round stopped.
//
// `?mode=join` is the same page for the files a first join left differing
// (board 6.4.23's "Choose versions"): the title and description are written
// for joining and the foot's primary is Apply choices.
//
// Which file is open lives in the URL (`?path=`), so the Status card's rows
// open the page at their file. Whether a file is open in the editor is this
// page's own state: the marked-up copy exists from the moment an agent is
// handed the file, so the copy alone does not mean the person chose to edit it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/status/StatusPill";
import { SyncConflictFileList } from "./SyncConflictFileList";
import { SyncConflictFooter } from "./SyncConflictFooter";
import { SyncConflictPane } from "./SyncConflictPane";
import { clock } from "./syncConflictFormat";
import { useResolveSource } from "./useResolveSource";

export function SyncResolveConflictsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const mode = params.get("mode") === "join" ? "join" : "conflicts";
  const join = mode === "join";
  const [editing, setEditing] = useState<ReadonlySet<string>>(new Set());
  const source = useResolveSource(mode);
  const files = source.files;
  const machine =
    files.find((f) => f.theirs_machine)?.theirs_machine ?? t("sync.conflicts.otherMachine");

  const header = (
    <PageHeader
      title={t(join ? "sync.resolve.join.title" : "sync.resolve.title")}
      badges={
        files.length > 0 ? (
          <StatusPill tone={join ? "warn" : "err"}>
            {t(join ? "sync.resolve.join.pill" : "sync.resolve.pill")}
          </StatusPill>
        ) : null
      }
      subtitle={
        files.length > 0
          ? join
            ? t("sync.resolve.join.subline", { machine })
            : t("sync.resolve.subline", {
                time: clock(source.raisedAt, i18n.language),
                machine,
              })
          : undefined
      }
    />
  );

  if (source.loading) {
    return (
      <div className="space-y-6">
        {header}
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }
  if (files.length === 0) {
    return (
      <div className="space-y-6">
        {header}
        <EmptyState
          title={t(join ? "sync.resolve.join.empty.title" : "sync.resolve.empty.title")}
          description={t(join ? "sync.resolve.join.empty.body" : "sync.resolve.empty.body")}
        />
      </div>
    );
  }

  const wanted = params.get("path");
  const file =
    files.find((f) => f.path === wanted) ?? files.find((f) => f.answer === null) ?? files[0]!;
  const setEditingFor = (path: string, on: boolean) =>
    setEditing((prev) => {
      const next = new Set(prev);
      if (on) next.add(path);
      else next.delete(path);
      return next;
    });
  const select = (path: string) => {
    const next = new URLSearchParams(params);
    next.set("path", path);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-6">
      {header}
      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
        <div className="flex min-h-[420px]">
          <SyncConflictFileList
            files={files}
            selected={file.path}
            editing={editing}
            onSelect={select}
          />
          <SyncConflictPane
            key={file.path}
            file={file}
            source={source}
            editing={editing.has(file.path) && file.answer === null && !file.secret}
            onEditing={(on) => setEditingFor(file.path, on)}
          />
        </div>
        <SyncConflictFooter source={source} onDone={() => navigate("/sync")} />
      </div>
    </div>
  );
}
