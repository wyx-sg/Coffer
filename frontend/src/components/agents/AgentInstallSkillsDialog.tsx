// frontend/src/components/agents/AgentInstallSkillsDialog.tsx
// Skill-picker dialog for installing Coffer-managed skills onto agent(s). It
// renders the full skills list through the shared DataTable — search, source
// filter, pagination, select-all and multi-select — and the selection bar
// carries the "Install (N)" action. Enabling is per-(skill, agent), so install
// fans out one enable mutation per (agent, checked skill) pair before closing.
import { useTranslation } from "react-i18next";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AgentOut } from "@/lib/api/agents";
import { skillsApi, type SkillOut } from "@/lib/api/skills";
import { useSkills } from "@/lib/hooks/useSkills";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentInstallSkillsDialog({
  agents,
  open,
  onOpenChange,
  onInstalled,
}: {
  agents: AgentOut[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInstalled?: () => void;
}) {
  const { t } = useTranslation();
  const skills = useSkills();
  const bulk = useBulkMutate({ invalidate: [["skills"]] });
  const items = skills.data ?? [];

  // One enable per (agent, skill) pair; bind every chosen skill to every agent.
  // allSettled so a single failing pair doesn't abandon the rest; the summary
  // toast reports the outcome, then we always close + clear (never stuck).
  const install = async (chosen: SkillOut[], clear: () => void) => {
    const pairs = agents.flatMap((a) => chosen.map((s) => ({ agent: a.name, skill: s.name })));
    await bulk.run(pairs, (p) => skillsApi.enable(p.skill, { agent_name: p.agent }));
    clear();
    onInstalled?.();
    onOpenChange(false);
  };

  const columns: Column<SkillOut>[] = [
    {
      key: "name",
      header: t("skills.name"),
      className: "whitespace-nowrap",
      cell: (s) => <span className="font-medium">{s.name}</span>,
    },
    {
      key: "source",
      header: t("skills.source"),
      className: "whitespace-nowrap",
      cell: (s) => <span className="text-muted-foreground">{s.source.type}</span>,
    },
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
  ];

  const filters: FilterDef<SkillOut>[] = [
    {
      key: "source",
      label: t("skills.source"),
      allLabel: t("skills.allSources"),
      accessor: (s) => s.source.type,
      options: [
        { value: "local_import", label: "local_import" },
        { value: "git", label: "git" },
      ],
    },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {t("agents.installSkillsDialog.title", { count: agents.length })}
          </DialogTitle>
          <DialogDescription>{t("agents.installSkillsDialog.subtitle")}</DialogDescription>
        </DialogHeader>

        {items.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            {t("agents.installSkillsDialog.empty")}
          </p>
        ) : (
          <DataTable
            rows={items}
            columns={columns}
            rowKey={(s) => s.name}
            search={{
              accessor: (s) => `${s.name} ${s.description}`,
              placeholder: t("skills.searchPlaceholder"),
            }}
            filters={filters}
            pageSize={8}
            selection={{
              ariaSelectAll: t("common.bulk.selectAll"),
              ariaSelectRow: (s) => `${t("common.bulk.selectRow")}: ${s.name}`,
              bulkLabel: (count) => t("common.bulk.selected", { count }),
              clearLabel: t("common.clear"),
              renderBulkActions: ({ selectedRows, clear }) => (
                <Button
                  size="sm"
                  disabled={bulk.isPending}
                  onClick={() => void install(selectedRows, clear)}
                >
                  {t("agents.installSkillsDialog.install", { count: selectedRows.length })}
                </Button>
              ),
            }}
            emptyMessage={t("skills.noMatches")}
          />
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
