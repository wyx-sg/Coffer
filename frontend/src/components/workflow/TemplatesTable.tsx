// frontend/src/components/workflow/TemplatesTable.tsx
// The template list: what each flow is called, what it is for, the stages it
// runs IN ORDER, and whether it is enabled (FR-054).
//
// The stages column COUNTS them. It used to spell the order out — `Design →
// Coding → Testing` — which is the shape of the flow and therefore the thing
// worth knowing, except that a list is read by scanning down a column and a
// six-stage chain is a paragraph in a cell. The shape is one click away, drawn
// properly, on the workflow's own page; here the useful fact is how big it is.
//
// Searching still matches the names: a developer looking for "the one with a
// Testing stage" is asking a question this column no longer shows but the
// template still answers.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { Switch } from "@/components/ui/switch";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { WORKFLOW_TEMPLATE_KIND } from "@/lib/api/workflow";
import type { WorkflowTemplate } from "@/lib/hooks/useWorkflowTemplates";

interface Props {
  templates: WorkflowTemplate[];
  isLoading?: boolean;
  onDelete: (template: WorkflowTemplate) => void;
}

/** The stage names, for the search box rather than for the eye. */
function stageNames(template: WorkflowTemplate): string {
  return (template.config.stages ?? []).map((s) => s.name || s.key).join(" ");
}

export function TemplatesTable({ templates, isLoading = false, onDelete }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const enable = useEnableResource();
  const disable = useDisableResource();
  const busy = enable.isPending || disable.isPending;

  const columns: Column<WorkflowTemplate>[] = [
    {
      key: "name",
      header: t("workflow.templates.cols.name"),
      className: "whitespace-nowrap",
      cell: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "description",
      header: t("workflow.templates.cols.description"),
      // `w-full max-w-0` is what lets the cell shrink far enough for `truncate`
      // to fire: without the zero max-width it sizes to its content instead.
      className: "w-full max-w-0",
      cell: (row) => (
        <span className="block truncate text-muted-foreground">
          {row.description ?? row.config.description ?? t("common.emptyValue")}
        </span>
      ),
    },
    {
      key: "stages",
      header: t("workflow.templates.cols.stages"),
      className: "whitespace-nowrap",
      cell: (row) => (
        <span className="text-muted-foreground">
          {t("workflow.templates.stageCount", { count: (row.config.stages ?? []).length })}
        </span>
      ),
    },
    {
      key: "enabled",
      header: t("workflow.templates.cols.enabled"),
      className: "whitespace-nowrap",
      // Enabled is two states and nothing else, so it is the control rather
      // than a badge you have to open the workflow to act on. The row itself
      // navigates, hence the stopped propagation: flipping the switch must not
      // also open the editor.
      cell: (row) => (
        <span onClick={(e) => e.stopPropagation()}>
          <Switch
            checked={row.enabled}
            disabled={busy}
            aria-label={t("workflow.templates.enabledAria", { name: row.name })}
            onCheckedChange={(next) => {
              const input = { kind: WORKFLOW_TEMPLATE_KIND, name: row.name };
              if (next) enable.mutate(input);
              else disable.mutate(input);
            }}
          />
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      cell: (row) => (
        <RowDeleteButton
          ariaLabel={`${t("workflow.templates.deleteTitle")}: ${row.name}`}
          onDelete={() => onDelete(row)}
        />
      ),
    },
  ];

  return (
    <DataTable
      rows={templates}
      isLoading={isLoading}
      columns={columns}
      rowKey={(row) => row.name}
      search={{
        accessor: (row) => `${row.name} ${row.description ?? ""} ${stageNames(row)}`,
        placeholder: t("workflow.templates.searchPlaceholder"),
      }}
      onRowClick={(row) => navigate(`/workflows/${encodeURIComponent(row.name)}`)}
      emptyMessage={t("workflow.templates.noMatches")}
    />
  );
}
