// frontend/src/components/skills/SkillsTable.tsx
//
// The skills list rendered via the shared DataTable (mirrors AgentTable): rows
// navigate to the skill detail page on click, search covers name + description,
// a reach filter narrows by reach, each row carries the three-state
// ScopeControl and a Delete icon+text action (the delete opens the shared
// ConfirmDialog — no window.confirm). Multi-select adds a bulk bar carrying
// that same three-state reach control over the whole selection, plus Delete.
// The per-row + bulk action UI lives in SkillsTableActions.tsx.
//
// The name cell also carries the copy_fallback "Copied" chip (FR-011): when a
// delivery had to fall back to a copy, the UI must say so, and this list is the
// only place the whole library is in view — the agent's Skills tab no longer
// repeats it.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import {
  SkillRowActions,
  SkillStatusCell,
  SkillsBulkActions,
} from "@/components/skills/SkillsTableActions";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SkillOut } from "@/lib/api/skills";
import { useRemoveSkill } from "@/lib/hooks/useSkills";
import { reachFilter } from "@/lib/reachFilter";

export function SkillsTable({
  skills,
  isLoading = false,
}: {
  skills: SkillOut[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useRemoveSkill();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const columns: Column<SkillOut>[] = [
    {
      key: "name",
      header: t("skills.name"),
      cell: (s) => (
        <span className="flex items-center gap-2">
          <span className="font-medium">{s.name}</span>
          {s.bindings.some((b) => b.link_mode === "copy_fallback") && (
            <Badge
              variant="outline"
              data-testid="skill-degraded-badge"
              className="border-status-warn/40 text-status-warn"
              title={t("skills.degradedTooltip")}
            >
              {t("skills.degradedBadge")}
            </Badge>
          )}
        </span>
      ),
    },
    // Source column intentionally hidden — every skill is local_import today, so
    // it carries no signal. The source field stays in the model (skills.source /
    // skills.allSources i18n keys retained) for when other origins (e.g. git
    // import) land and the column/filter become meaningful again.
    {
      key: "description",
      header: t("skills.description"),
      cell: (s) =>
        s.description ? (
          <span className="line-clamp-1 max-w-md text-muted-foreground">{s.description}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "reach",
      header: t("resources.cols.reach"),
      className: "text-right",
      cell: (s) => <SkillStatusCell skill={s} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (s) => (
        <SkillRowActions
          skill={s}
          deleteDisabled={remove.isPending}
          onDelete={() => setDeletingName(s.name)}
        />
      ),
    },
  ];

  // Source filter intentionally hidden alongside the source column (see above).
  // The reach filter follows the reach column — the same three states every
  // scoped-resource list offers.
  const filters = [reachFilter(t, (s: SkillOut) => ({ enabled: s.enabled, scope: s.scope }))];

  return (
    <>
      <DataTable
        rows={skills}
        isLoading={isLoading}
        columns={columns}
        rowKey={(s) => s.name}
        search={{
          accessor: (s) => `${s.name} ${s.description}`,
          placeholder: t("skills.searchPlaceholder"),
        }}
        filters={filters}
        onRowClick={(s) => navigate(`/skills/${s.name}`)}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (s) => `${t("common.bulk.selectRow")}: ${s.name}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          renderBulkActions: ({ selectedRows, clear }) => (
            <SkillsBulkActions skills={selectedRows} onDone={clear} />
          ),
        }}
        emptyMessage={t("skills.noMatches")}
      />

      <ConfirmDialog
        open={deletingName !== null}
        onOpenChange={(o) => !o && setDeletingName(null)}
        title={t("skills.removeConfirmTitle", { name: deletingName ?? "" })}
        description={t("skills.removeConfirmBody")}
        confirmLabel={remove.isPending ? t("common.deleting") : t("common.delete")}
        pending={remove.isPending}
        onConfirm={() => {
          // Close only on success; the hook toasts a failure and the dialog
          // stays up so the reader can retry or cancel.
          if (deletingName) {
            remove.mutate(deletingName, { onSuccess: () => setDeletingName(null) });
          }
        }}
      />
    </>
  );
}
