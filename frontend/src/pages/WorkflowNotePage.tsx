// frontend/src/pages/WorkflowNotePage.tsx — one note the developer wrote
// (spec workflow, FR-069).
//
// A page rather than a dialog, for the same reason a produced file gets one:
// this is something you read, come back to, and send someone the link to. The
// difference is that it is also something you WRITE — a note is the one thing
// in a run's context that is the developer's own words, and a thought is not
// finished when it was first written down.
//
// Read mode renders the markdown; write mode is a textarea that accepts a
// pasted screenshot. Two modes and not one live preview: the run is going
// while this page is open, and a box that re-rendered on every keystroke would
// be the noisiest thing on screen.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Eye, NotebookPen, Pencil } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Markdown } from "@/components/Markdown";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { NoteEditor } from "@/components/workflow/NoteEditor";
import { translateApiError } from "@/lib/api/errors";
import { useRunImages } from "@/lib/hooks/useRunImages";
import { useRewriteWorkflowNote, useWorkflowInputs } from "@/lib/hooks/useWorkflowInputs";
import { useWorkflowRunFile } from "@/lib/hooks/useWorkflowRun";

export function WorkflowNotePage() {
  const { t } = useTranslation();
  const { runId = "", noteRef = "" } = useParams<{ runId: string; noteRef: string }>();
  const stored = useWorkflowRunFile(runId, noteRef.length > 0 ? `inputs/${noteRef}` : null);
  const inputs = useWorkflowInputs(runId);
  const rewrite = useRewriteWorkflowNote(runId);
  const [draft, setDraft] = useState<string | null>(null);

  const text = stored.data?.text ?? "";
  const images = useRunImages(runId, draft ?? text);
  const note = (inputs.data ?? []).find((item) => item.ref === noteRef);
  const title = note?.label ?? noteRef;

  const back = { to: `/runs/${runId}?tab=context`, label: t("workflow.context.backToRun") };

  if (stored.isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-64" />} />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (stored.error || stored.data === undefined) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={noteRef} />
        <EmptyState
          icon={NotebookPen}
          title={t("workflow.notes.notFound")}
          description={stored.error ? translateApiError(t, stored.error) : undefined}
        />
      </div>
    );
  }

  const editing = draft !== null;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={NotebookPen}
        back={back}
        title={title}
        subtitle={t("workflow.notes.subtitle")}
        actions={
          editing ? (
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={() => setDraft(null)}>
                {t("common.cancel")}
              </Button>
              <Button
                disabled={rewrite.isPending}
                onClick={() =>
                  rewrite.mutate(
                    { ref: noteRef, text: draft },
                    {
                      onSuccess: () => {
                        void stored.refetch();
                        setDraft(null);
                      },
                    },
                  )
                }
              >
                <Eye aria-hidden />
                {t("workflow.notes.save")}
              </Button>
            </div>
          ) : (
            <Button variant="outline" onClick={() => setDraft(text)}>
              <Pencil aria-hidden />
              {t("workflow.notes.edit")}
            </Button>
          )
        }
      />

      {editing ? (
        <NoteEditor
          runId={runId}
          value={draft}
          onChange={setDraft}
          disabled={rewrite.isPending}
        />
      ) : text.trim().length === 0 ? (
        <EmptyState
          icon={NotebookPen}
          title={t("workflow.notes.emptyTitle")}
          description={t("workflow.notes.emptyBody")}
        />
      ) : (
        <div className="rounded-lg border border-border bg-card p-6">
          <Markdown resolveImage={(src) => images[src]}>{text}</Markdown>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        <Link className="hover:underline" to={`/runs/${runId}/files?path=inputs/${noteRef}`}>
          {t("workflow.notes.asFile", { ref: noteRef })}
        </Link>
      </p>
    </div>
  );
}
