// frontend/src/components/workflow/NodeContextRail.tsx
// What this task is working FROM, beside the conversation doing the work.
//
// A task opens with the run's whole shared context (FR-029) — the mounted
// inputs, the notes, everything earlier tasks produced — and until now the
// only way to see any of it was to leave the conversation for the run's own
// page and come back. The transcript talks about `td.md`; this is where you
// read `td.md` without losing your place in the sentence that mentioned it.
//
// The SAME rows the run's context table builds, from the same function. Two
// lists of "what is in this run" would eventually disagree about whether a
// note is a file, and this one would be the one nobody maintained.
//
// Clicking a file opens it HERE, in place of the list, with a way back. The
// alternative was a page, and a page is a thing you navigate away to: the
// whole point of this panel is that the conversation stays on screen.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ExternalLink, FileText, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { RunFileView } from "@/components/workflow/RunFileView";
import { useWorkflowInputs } from "@/lib/hooks/useWorkflowInputs";
import { useWorkflowArtifacts } from "@/lib/hooks/useWorkflowRun";
import { buildContextRows, type ContextRow } from "@/lib/workflow/contextRows";

interface Props {
  runId: string;
  /** Closes the panel. It can be closed at any width, because it can be opened
   *  at any width — a panel that only exists on big screens is a panel half
   *  the people never see. */
  onClose: () => void;
}

export function NodeContextRail({ runId, onClose }: Props) {
  const { t } = useTranslation();
  const inputs = useWorkflowInputs(runId);
  const artifacts = useWorkflowArtifacts(runId);
  const [reading, setReading] = useState<{ path: string; name: string } | null>(null);

  const rows = buildContextRows(inputs.data ?? [], artifacts.data?.items ?? []);
  const loading = inputs.isPending || artifacts.isPending;

  if (reading !== null) {
    return (
      <Panel>
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("workflow.context.backToList")}
            onClick={() => setReading(null)}
          >
            <ArrowLeft className="size-4" aria-hidden />
          </Button>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{reading.name}</span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
          <RunFileView runId={runId} path={reading.path} />
        </div>
      </Panel>
    );
  }

  return (
    <Panel>
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="flex-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("workflow.tabs.context")}
        </span>
        <Button variant="ghost" size="icon-sm" aria-label={t("common.close")} onClick={onClose}>
          <X className="size-4" aria-hidden />
        </Button>
      </div>
      <div className="min-h-0 flex-1 space-y-1 overflow-auto p-2">
        {loading ? (
          <Skeleton className="h-16 w-full" />
        ) : rows.length === 0 ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">
            {t("workflow.context.emptyBody")}
          </p>
        ) : (
          rows.map((row) => <Row key={row.id} row={row} onRead={setReading} />)
        )}
      </div>
    </Panel>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <aside className="flex h-full min-h-0 flex-col border-l border-border" aria-label="context">
      {children}
    </aside>
  );
}

function Row({
  row,
  onRead,
}: {
  row: ContextRow;
  onRead: (file: { path: string; name: string }) => void;
}) {
  const { t } = useTranslation();
  const inner = (
    <>
      <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1 truncate">{row.name}</span>
      {/* The same word the table uses, and the same word the node was told a
          link is (FR-065) — one vocabulary for one thing. */}
      <span className="shrink-0 text-[10px] text-muted-foreground">
        {row.kind === "artifact"
          ? t("workflow.context.artifact")
          : row.provider !== null
            ? t(`workflow.inputs.providers.${row.provider}`, { defaultValue: row.provider })
            : t(`workflow.inputs.kinds.${row.kind}`)}
      </span>
    </>
  );
  const shell =
    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  // A link leaves the app; everything else this panel can show, it shows.
  if (row.open?.how === "url") {
    return (
      <a className={shell} href={row.open.href} target="_blank" rel="noreferrer noopener">
        {inner}
        <ExternalLink className="size-3 shrink-0 opacity-60" aria-hidden />
      </a>
    );
  }
  const path =
    row.open?.how === "preview"
      ? row.open.path
      : row.open?.how === "note"
        ? `inputs/${row.open.ref}`
        : null;
  if (path === null) {
    return <span className={`${shell} cursor-default hover:bg-transparent`}>{inner}</span>;
  }
  return (
    <button type="button" className={shell} onClick={() => onRead({ path, name: row.name })}>
      {inner}
    </button>
  );
}
