// src/pages/UnmanagedSkillDetailPage.tsx — one skill folder Coffer does not manage, at /agents/:type/skills/unmanaged/:location/:name.
//
// Spec skill-manager "Preview an unmanaged skill read-only" and "Act on an
// unmanaged skill from its detail page" (boards 2.1.57, 2.1.58). Reached from
// the name on the agent's Skills tab. The standard detail header — the skill's
// name in the mono face, an "Unmanaged" pill, the meta line "<agent>’s own
// skill · <folder> · N files", Adopt as the one button and a ⋯ that holds only
// Delete… — over two tabs (Overview and Files, the open one in `?tab=`).
// Overview is property rows; Files is the folder's tree beside a read-only
// viewer. Everything here reads; the header's two actions change something.
// The folder has no uid: it is addressed by the agent's type, the scan location
// and the folder name, and the way out is the sidebar or the agent's Skills tab.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Sparkle } from "lucide-react";

import { AdoptSkillDialog } from "@/components/agents/skills/AdoptSkillDialog";
import { DeleteOwnSkillDialog } from "@/components/agents/skills/DeleteOwnSkillDialog";
import { ownSkillKey, type OwnSkillRow } from "@/components/agents/skills/skillRows";
import { UnmanagedSkillFiles } from "@/components/agents/UnmanagedSkillFiles";
import { UnmanagedSkillOverview } from "@/components/agents/UnmanagedSkillOverview";
import { EmptyState } from "@/components/EmptyState";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import { translateApiError } from "@/lib/api/errors";
import type { SkillFileNode } from "@/lib/api/skills";
import { useDeleteUnmanagedSkill } from "@/lib/hooks/useAgents";
import { useAgentRoute } from "@/lib/hooks/useAgentRoute";
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";
import { useUnmanagedSkill, useUnmanagedSkillFiles } from "@/lib/hooks/useUnmanagedSkill";

/** The relative path of every file under the folder, in tree order. */
function filePaths(node: SkillFileNode | undefined): string[] {
  if (!node) return [];
  if (node.type === "file") return [node.path || node.name];
  return node.children.flatMap(filePaths);
}

export function UnmanagedSkillDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { location = "", name = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const route = useAgentRoute();
  const uid = route.uid;
  const { data: skill, isPending: skillPending, error } = useUnmanagedSkill(uid, location, name);
  const files = useUnmanagedSkillFiles(uid, location, name);
  const remove = useDeleteUnmanagedSkill(uid);
  const [adoptOpen, setAdoptOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const isPending = route.isPending || (uid !== "" && skillPending);

  const skillsTab = route.type ? agentTabPath(route.type, "skills") : "/agents";
  const agentName = agentTypeLabel(route.type ?? "");

  const setTab = (next: string) =>
    setParams(
      (prev) => {
        if (next === "overview") prev.delete("tab");
        else prev.set("tab", next);
        return prev;
      },
      { replace: true },
    );

  if (isPending) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-80" />
      </div>
    );
  }
  if (error || route.error || !skill) {
    return (
      <EmptyState
        icon={Sparkle}
        title={t("agents.skillsTab.unmanagedDetail.notFound")}
        description={error || route.error ? translateApiError(t, error ?? route.error) : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to={skillsTab}>
              <ArrowLeft className="mr-1 size-4" />
              {t("agents.workspace.skills")}
            </Link>
          </Button>
        }
      />
    );
  }

  const paths = filePaths(files.data);
  const row: OwnSkillRow = {
    key: ownSkillKey(skill),
    name: skill.name,
    item: skill,
    state: skill.foreign_link ? "foreign" : skill.valid ? "unmanaged" : "invalid",
    duplicateOf: null,
  };
  // Adopt is offered only for a folder that can be adopted (a valid SKILL.md,
  // not a link to somewhere else).
  const adoptable = skill.valid && !skill.foreign_link;
  const meta = [
    t("agents.skillsTab.unmanagedDetail.ownSkill", { agent: agentName }),
    abbreviateHomePath(skill.path),
    paths.length > 0 ? t("agents.skillsTab.unmanagedDetail.files", { count: paths.length }) : null,
  ].filter((part): part is string => Boolean(part));

  return (
    <div className="space-y-4">
      <PageHeader
        title={<span className="font-mono text-lg font-semibold">{skill.name}</span>}
        badges={<StatusPill tone="off">{t("agents.skillsTab.unmanagedBadge")}</StatusPill>}
        subtitle={meta.join(" · ")}
        actions={
          <>
            {adoptable ? (
              <Button onClick={() => setAdoptOpen(true)}>{t("agents.skillsTab.adopt")}</Button>
            ) : null}
            <ActionMenu
              label={t("agents.kindTab.moreFor", { name: skill.name })}
              actions={[
                {
                  key: "delete",
                  label: t("agents.skillsTab.menu.delete"),
                  destructive: true,
                  onSelect: () => setDeleteOpen(true),
                },
              ]}
            />
          </>
        }
      />

      {!skill.valid ? (
        <LoadErrorRow
          title={t("agents.skillsTab.unmanagedDetail.invalidTitle")}
          reason={skill.reason ?? undefined}
        />
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("skills.detail.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="files">{t("skills.detail.tabs.files")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-4">
          <UnmanagedSkillOverview
            skill={skill}
            agentName={agentName}
            fileCount={paths.length}
            onShowFiles={() => setTab("files")}
          />
        </TabsContent>

        <TabsContent value="files" className="pt-4">
          <UnmanagedSkillFiles agentUid={uid} location={location} name={name} />
        </TabsContent>
      </Tabs>

      <AdoptSkillDialog
        agentUid={uid}
        row={adoptOpen ? row : null}
        onOpenChange={(open) => {
          setAdoptOpen(open);
        }}
      />
      <DeleteOwnSkillDialog
        agentUid={uid}
        target={deleteOpen ? row : null}
        pending={remove.isPending}
        onOpenChange={setDeleteOpen}
        onConfirm={(target) =>
          // Close only on success; the hook toasts a failure.
          remove.mutate(
            { skill: target.name, location: target.item.location },
            {
              onSuccess: () => {
                setDeleteOpen(false);
                navigate(skillsTab);
              },
            },
          )
        }
      />
    </div>
  );
}
