// frontend/src/components/agents/AgentUnmanagedSkills.tsx — spec skill-manager,
// unmanaged skills.
// "Unmanaged skills" section of the agent Skills tab: skills found on disk in
// the agent's skill locations that Coffer does not manage, with adopt-into-
// master and delete actions. Foreign symlinks (targets outside the master
// store) are badged and never adoptable. Hidden entirely while the list is
// empty. Extracted from AgentSkillsTab to keep that file inside the
// component size cap.
//
// Rendered through the shared DataTable so it mirrors the "Managed by Coffer"
// table directly above it — same header row, search box, and pagination —
// differing only in the per-row actions (adopt/delete). There is no status
// filter here: an on-disk unmanaged skill has no enable/disable state to filter
// on, so the toolbar carries the search box alone.
//
// Clicking a row opens that folder's detail page (UnmanagedSkillDetailPage):
// Coffer doesn't manage these skills, so reading the SKILL.md and the files is
// how the user decides whether to adopt or delete one, and that page previews
// them read-only and carries the open-folder action. Adopt/delete failures
// toast from the hooks; only the adopt success is confirmed here.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentUnmanagedSkillsBulkActions } from "@/components/agents/AgentUnmanagedSkillsBulkActions";
import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { UnmanagedSkillOut } from "@/lib/api/agents";
import { unmanagedSkillPath } from "@/lib/agents/unmanagedSkillPath";
import {
  useAdoptUnmanagedSkill,
  useDeleteUnmanagedSkill,
  useUnmanagedSkills,
} from "@/lib/hooks/useAgents";

export function UnmanagedSkillsSection({ agentUid }: { agentUid: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const unmanaged = useUnmanagedSkills(agentUid);
  const adopt = useAdoptUnmanagedSkill(agentUid);
  const remove = useDeleteUnmanagedSkill(agentUid);
  const navigate = useNavigate();
  const [deleteTarget, setDeleteTarget] = useState<UnmanagedSkillOut | null>(null);

  const items = unmanaged.data?.items ?? [];
  // Keep the section hidden until there is at least one unmanaged skill to act
  // on, so it never adds an empty table to the page.
  if (items.length === 0) return null;

  const columns: Column<UnmanagedSkillOut>[] = [
    {
      key: "name",
      header: t("skills.name"),
      className: "whitespace-nowrap",
      cell: (s) => (
        <span className="flex items-center gap-2">
          <span className="font-medium">{s.name}</span>
          <Badge variant="outline">
            {s.location === "agents_dir"
              ? t("agents.skillsTab.locationAgentsDir")
              : t("agents.skillsTab.locationSkills")}
          </Badge>
          {s.foreign_link && (
            <Badge
              variant="outline"
              data-testid="foreign-link-badge"
              className="border-status-warn/50 text-status-warn"
            >
              {t("agents.skillsTab.foreignLink")}
            </Badge>
          )}
        </span>
      ),
    },
    {
      key: "description",
      header: t("skills.description"),
      cell: (s) =>
        !s.valid && s.reason ? (
          <span className="line-clamp-1 max-w-md text-muted-foreground">{s.reason}</span>
        ) : (
          <span className="text-muted-foreground">{t("common.emptyValue")}</span>
        ),
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (s) => {
        const adoptHint = !s.valid
          ? t("agents.skillsTab.adoptDisabledInvalid")
          : s.foreign_link
            ? t("agents.skillsTab.adoptDisabledForeign")
            : undefined;
        return (
          // The row itself navigates, so a click on an action stops here.
          <span className="flex justify-end gap-2" onClick={(e) => e.stopPropagation()}>
            {/* Wrapper span carries the disabled-reason tooltip — the disabled
                button itself has pointer-events:none so it can't show one. */}
            <span title={adoptHint}>
              <Button
                size="sm"
                variant="outline"
                disabled={!s.valid || s.foreign_link || adopt.isPending}
                onClick={() =>
                  adopt.mutate(
                    { skill: s.name, location: s.location },
                    {
                      onSuccess: () =>
                        toast.success(t("agents.skillsTab.adoptSuccess", { name: s.name })),
                    },
                  )
                }
              >
                {t("agents.skillsTab.adopt")}
              </Button>
            </span>
            <Button
              size="sm"
              variant="outline"
              className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setDeleteTarget(s)}
            >
              {t("common.delete")}
            </Button>
          </span>
        );
      },
    },
  ];

  return (
    <Card className="space-y-3 p-4" data-testid="unmanaged-skills">
      <h3 className="text-sm font-medium text-muted-foreground">
        {t("agents.skillsTab.unmanagedTitle")}
      </h3>

      <DataTable
        rows={items}
        columns={columns}
        rowKey={(s) => `${s.location}:${s.name}`}
        onRowClick={(s) => navigate(unmanagedSkillPath(agentUid, s.location, s.name))}
        search={{
          accessor: (s) => `${s.name} ${s.reason ?? ""}`,
          placeholder: t("skills.searchPlaceholder"),
        }}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (s) => `${t("common.bulk.selectRow")}: ${s.name}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          renderBulkActions: ({ selectedRows, clear }) => (
            <AgentUnmanagedSkillsBulkActions
              agentUid={agentUid}
              rows={selectedRows}
              clear={clear}
            />
          ),
        }}
        emptyMessage={t("agents.skillsTab.unmanagedNoMatch")}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t("agents.removeConfirmTitle", { name: deleteTarget?.name ?? "" })}
        description={t("agents.skillsTab.deleteConfirm")}
        confirmLabel={t("common.delete")}
        pending={remove.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          remove.mutate(
            { skill: deleteTarget.name, location: deleteTarget.location },
            { onSuccess: () => setDeleteTarget(null) },
          );
        }}
      />
    </Card>
  );
}
