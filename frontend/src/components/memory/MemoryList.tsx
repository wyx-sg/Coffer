// frontend/src/components/memory/MemoryList.tsx
//
// The open project's topic files, beside the project list (spec memory "Show
// and edit memory on the Memory page"). The header names the project folder
// and how many files it holds; each row shows the topic's title and its first
// memory, its type and when it was last updated, and a warning when the file
// breaks the format. Search and the type filter narrow the list; a row opens
// the file in the drawer.
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { TruncatedText } from "@/components/ui/truncated-text";
import type { MemoryProject, MemoryTopic } from "@/lib/api/memoryTypes";
import { projectName } from "@/lib/memory/projects";

interface Props {
  project: MemoryProject;
  topics: MemoryTopic[];
  isLoading?: boolean;
  onOpen: (topic: MemoryTopic) => void;
}

const TYPES = ["user", "feedback", "project"] as const;

export function MemoryList({ project, topics, isLoading = false, onOpen }: Props) {
  const { t } = useTranslation();
  const typeLabel = (type: string) =>
    t(`memory.type.${(TYPES as readonly string[]).includes(type) ? type : "none"}`);

  const columns: Column<MemoryTopic>[] = [
    {
      key: "topic",
      header: t("memory.topics.cols.topic"),
      cell: (m) => (
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="inline-flex min-w-0 items-center gap-1.5">
            <TruncatedText text={m.title} className="text-sm font-medium" />
            {m.problems.length > 0 ? (
              <AlertTriangle
                className="size-3.5 shrink-0 text-warning"
                aria-label={t("memory.problem.title")}
              />
            ) : null}
          </span>
          <TruncatedText
            text={m.body.split("\n").find((l) => l.trim()) ?? ""}
            className="text-xs text-text-muted"
          />
        </div>
      ),
    },
    {
      key: "type",
      header: t("memory.topics.cols.type"),
      className: "w-[110px]",
      cell: (m) => <span className="text-xs text-text-muted">{typeLabel(m.type)}</span>,
    },
    {
      key: "updated",
      header: t("memory.topics.cols.updated"),
      className: "w-[100px] whitespace-nowrap",
      cell: (m) => <span className="font-mono text-xs text-text-muted">{m.updated}</span>,
    },
  ];

  return (
    <div className="flex flex-col gap-4" data-testid="memory-list">
      <header className="flex min-w-0 flex-col gap-1">
        <h2 className="text-lg font-semibold">{projectName(project.folder)}</h2>
        <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-text-muted">
          <span className="font-mono">{project.folder}</span>
          <span aria-hidden>·</span>
          <span>{t("memory.topics.files", { count: project.topics })}</span>
        </p>
      </header>
      <DataTable
        fixed
        rows={topics}
        isLoading={isLoading}
        columns={columns}
        search={{
          accessor: (m) => `${m.title} ${m.body}`,
          placeholder: t("memory.topics.search"),
        }}
        filters={[
          {
            key: "type",
            label: t("memory.topics.filters.type"),
            options: TYPES.map((v) => ({ value: v, label: typeLabel(v) })),
            accessor: (m) => m.type,
          },
        ]}
        rowKey={(m) => m.name}
        onRowClick={onOpen}
        emptyMessage={t("memory.topics.empty")}
      />
    </div>
  );
}
