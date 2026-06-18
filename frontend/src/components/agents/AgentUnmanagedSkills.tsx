// frontend/src/components/agents/AgentUnmanagedSkills.tsx — spec 005 FR-022..024.
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
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { UnmanagedSkillOut } from "@/lib/api/agents";
import {
  useAdoptUnmanagedSkill,
  useDeleteUnmanagedSkill,
  useUnmanagedSkills,
} from "@/lib/hooks/useAgents";

export function UnmanagedSkillsSection({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const unmanaged = useUnmanagedSkills(agentName);
  const adopt = useAdoptUnmanagedSkill(agentName);
  const remove = useDeleteUnmanagedSkill(agentName);
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
              className="border-amber-500/50 text-amber-600 dark:text-amber-400"
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
          <span className="text-muted-foreground">—</span>
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
          <span className="flex justify-end gap-2">
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
                      onError: (e) => toast.error(translateApiError(t, e)),
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
        search={{
          accessor: (s) => `${s.name} ${s.reason ?? ""}`,
          placeholder: t("skills.searchPlaceholder"),
        }}
        emptyMessage={t("agents.skillsTab.unmanagedNoMatch")}
      />

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("common.delete")}: {deleteTarget?.name}
            </DialogTitle>
            <DialogDescription>{t("agents.skillsTab.deleteConfirm")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (!deleteTarget) return;
                remove.mutate(
                  { skill: deleteTarget.name, location: deleteTarget.location },
                  {
                    onSuccess: () => setDeleteTarget(null),
                    onError: (e) => toast.error(translateApiError(t, e)),
                  },
                );
              }}
            >
              {t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
