// frontend/src/components/memory/MemoryPreviewPanel.tsx
//
// A first or large sync waiting for the person (spec memory "Preview a first or
// large sync"): the hub is already up to date, but nothing is written into an
// agent until **Write**. One row per agent and project with how many copies
// would be written, updated and removed; a row opens that project's memories.
// **Write** writes exactly what is listed; **Cancel** drops the preview, and the
// next sync plans again.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { DataTable, type Column } from "@/components/DataTable";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { TruncatedText } from "@/components/ui/truncated-text";
import { agentTypeLabel } from "@/lib/agents/display";
import type { SyncProject } from "@/lib/api/memoryTypes";
import { useCancelPreview, useWritePreview } from "@/lib/hooks/useMemory";
import { projectPathByKey, type PreviewRow, type SyncPreview } from "@/lib/memory/syncFacts";

interface Props {
  preview: SyncPreview;
  projects: readonly SyncProject[];
}

const count = (n: number) => <span className="tabular-nums">{n > 0 ? n : "–"}</span>;

export function MemoryPreviewPanel({ preview, projects }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const write = useWritePreview();
  const cancel = useCancelPreview();
  const busy = write.isPending || cancel.isPending;
  const pathOf = (r: PreviewRow) => projectPathByKey(projects, r.project);

  const columns: Column<PreviewRow>[] = [
    {
      key: "agent",
      header: t("memory.preview.cols.agent"),
      className: "w-[180px]",
      cell: (r) => <AgentBadge type={r.agent} name={agentTypeLabel(r.agent)} size="sm" showName />,
    },
    {
      key: "project",
      header: t("memory.preview.cols.project"),
      cell: (r) => (
        <TruncatedText
          text={r.project || t("memory.projects.global")}
          className={r.project ? "font-mono text-xs" : "text-sm"}
        />
      ),
    },
    {
      key: "write",
      header: t("memory.preview.cols.write"),
      className: "w-[90px] text-right",
      cell: (r) => count(r.write),
    },
    {
      key: "update",
      header: t("memory.preview.cols.update"),
      className: "w-[90px] text-right",
      cell: (r) => count(r.update),
    },
    {
      key: "remove",
      header: t("memory.preview.cols.remove"),
      className: "w-[90px] text-right",
      cell: (r) => count(r.remove),
    },
  ];

  return (
    <Section
      as="h2"
      title={t("memory.preview.title", { count: preview.copies })}
      testId="memory-preview"
      actions={
        <>
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => cancel.mutate()}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            loading={write.isPending}
            disabled={busy}
            onClick={() => write.mutate()}
          >
            {t("memory.preview.write")}
          </Button>
        </>
      }
    >
      <p className="text-xs text-text-muted">{t("memory.preview.description")}</p>
      <DataTable
        fixed
        footer={false}
        rows={preview.rows}
        columns={columns}
        rowKey={(r) => `${r.agent}:${r.project}`}
        isRowClickable={(r) => pathOf(r) !== null}
        onRowClick={(r) => {
          const to = pathOf(r);
          if (to) navigate(to);
        }}
        emptyMessage={t("memory.preview.empty")}
      />
    </Section>
  );
}
