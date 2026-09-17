// frontend/src/components/workflow/TemplatesTable.tsx
// The template list: what each flow is called, what it is for, the stages it
// runs IN ORDER, and whether it is enabled (FR-054).
//
// The stages column spells the order out — `Design → Coding → Testing` — rather
// than counting them. The order is the flow (FR-005), so a count would hide the
// one thing a reader is scanning the list for.
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

/** The stages in order, as one readable line. */
function stageSummary(template: WorkflowTemplate): string {
  return (template.config.stages ?? []).map((s) => s.name || s.key).join(" → ");
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
      className: "w-full min-w-[14rem]",
      cell: (row) => (
        <span className="text-muted-foreground">
          {row.description ?? row.config.description ?? t("common.emptyValue")}
        </span>
      ),
    },
    {
      key: "stages",
      header: t("workflow.templates.cols.stages"),
      cell: (row) => <span className="text-muted-foreground">{stageSummary(row)}</span>,
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
        accessor: (row) => `${row.name} ${row.description ?? ""} ${stageSummary(row)}`,
        placeholder: t("workflow.templates.searchPlaceholder"),
      }}
      onRowClick={(row) => navigate(`/workflows/${encodeURIComponent(row.name)}`)}
      emptyMessage={t("workflow.templates.noMatches")}
    />
  );
}
