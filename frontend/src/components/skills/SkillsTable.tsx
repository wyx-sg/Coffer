// frontend/src/components/skills/SkillsTable.tsx
//
// The skills list rendered via the shared DataTable (mirrors AgentTable): rows
// navigate to the skill detail page on click, search covers name + description,
// a source filter narrows by origin, and each row carries Verify + Delete
// icon+text actions (the delete opens a styled confirmation dialog — no
// window.confirm). Multi-select adds a bulk Verify + bulk Delete bar. The
// per-row + bulk action UI lives in SkillsTableActions.tsx.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { SkillRowActions, SkillsBulkActions } from "@/components/skills/SkillsTableActions";
import { SkillVerifyDialog } from "@/components/skills/SkillVerifyDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SkillOut } from "@/lib/api/skills";
import { useRemoveSkill } from "@/lib/hooks/useSkills";

export function SkillsTable({ skills }: { skills: SkillOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useRemoveSkill();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);
  // Verify dialog is hoisted to the table level (not rendered inside the row)
  // so closing it can't fall through to the row's navigate-to-detail click.
  const [verifyingName, setVerifyingName] = useState<string | null>(null);

  const columns: Column<SkillOut>[] = [
    {
      key: "name",
      header: t("skills.name"),
      cell: (s) => <span className="font-medium">{s.name}</span>,
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
      key: "actions",
      header: "",
      className: "text-right",
      cell: (s) => (
        <SkillRowActions
          skill={s}
          deleteDisabled={remove.isPending}
          onVerify={() => setVerifyingName(s.name)}
          onDelete={() => setDeletingName(s.name)}
        />
      ),
    },
  ];

  // Source filter intentionally hidden alongside the source column (see above).
  const filters: FilterDef<SkillOut>[] = [];

  return (
    <>
      <DataTable
        rows={skills}
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

      <Dialog open={deletingName !== null} onOpenChange={(o) => !o && setDeletingName(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("skills.removeConfirmTitle", { name: deletingName ?? "" })}
            </DialogTitle>
            <DialogDescription>{t("skills.removeConfirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeletingName(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (deletingName) {
                  remove.mutate(deletingName, { onSuccess: () => setDeletingName(null) });
                }
              }}
            >
              {remove.isPending ? t("common.deleting") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <SkillVerifyDialog
        open={verifyingName !== null}
        skillNames={verifyingName ? [verifyingName] : undefined}
        onOpenChange={(o) => !o && setVerifyingName(null)}
      />
    </>
  );
}
