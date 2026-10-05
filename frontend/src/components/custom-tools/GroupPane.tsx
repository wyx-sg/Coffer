// src/components/custom-tools/GroupPane.tsx — the selected group: header and banners, then the tabs Overview
// (definition, Last 24 hours, Requires, most-called tools) · Tools (the tools table with each tool's exposure), the
// tab in the path (`/custom-tools/<group>/tools`; spec web-ui "Lay out every detail page's tabs alike"); the tool
// drawer, Edit group, Re-import and Delete over it.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Wrench } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useDetailTab } from "@/lib/detailTabs";
import { useAgents } from "@/lib/hooks/useAgents";
import { useCustomToolGroup } from "@/lib/hooks/useCustomTools";
import { useMcpInvocationSummary, useMcpToolTiering } from "@/lib/hooks/useMcpServerPage";
import { CUSTOM_TOOL_TABS } from "./customToolTabs";
import { DeleteGroupDialog } from "./DeleteGroupDialog";
import { EditGroupDialog } from "./EditGroupDialog";
import { GroupHeader } from "./GroupHeader";
import { GroupBanners } from "./GroupBanners";
import { GroupOverview } from "./GroupOverview";
import { groupToolRows } from "./overviewRows";
import { ReimportDialog } from "./ReimportDialog";
import { ToolEditorDrawer } from "./ToolEditorDrawer";
import { ToolsTable } from "./ToolsTable";

interface Props {
  name: string;
  /** Add request: the Add custom tool flow's request form, on this group. */
  onAddRequest: () => void;
}

export function GroupPane({ name, onAddRequest }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: group, isPending, error } = useCustomToolGroup(name);
  const [tool, setTool] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [reimportOpen, setReimportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const { data: agents = [] } = useAgents();
  // A group is an `mcp_server`: its 24-hour summary and tiering are the server page's reads, by uid.
  const uid = group?.uid ?? "";
  const summary = useMcpInvocationSummary(uid);
  const { data: tiering } = useMcpToolTiering(uid);
  const basePath = `/custom-tools/${encodeURIComponent(name)}`;
  const [tab, setTab] = useDetailTab(CUSTOM_TOOL_TABS, "overview", basePath, {
    enabled: group !== undefined,
  });

  if (isPending) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  // A group the daemon does not know is gone; any other failure keeps its own message.
  if (error instanceof ApiError && error.code.endsWith("NOT_FOUND")) {
    return <DetailNotFound kind="customTools" id={name} backTo="/custom-tools" icon={Wrench} />;
  }
  if (error || !group) {
    return (
      <EmptyState
        icon={Wrench}
        tone="error"
        title={t("errors.CUSTOM_TOOL_NOT_FOUND")}
        description={error ? translateApiError(t, error) : undefined}
      />
    );
  }

  const rows = groupToolRows(group, tiering);

  return (
    <div className="space-y-6 px-7 py-6">
      <GroupHeader
        group={group}
        onEdit={() => setEditOpen(true)}
        onDelete={() => setDeleteOpen(true)}
      />
      <GroupBanners group={group} onChooseAnother={() => setEditOpen(true)} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("customTools.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="tools">{t("customTools.tabs.tools")}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="pt-5">
          <GroupOverview
            group={group}
            agents={agents}
            summary={summary.data}
            summaryPending={summary.isPending}
            rows={rows}
            toolsHref={`${basePath}/tools`}
            onReimport={() => setReimportOpen(true)}
          />
        </TabsContent>
        <TabsContent value="tools" className="pt-5">
          <ToolsTable
            group={group}
            rows={rows}
            showExposure={tiering?.enabled ?? false}
            onOpenTool={setTool}
            onAddRequest={onAddRequest}
          />
        </TabsContent>
      </Tabs>
      <ToolEditorDrawer
        group={group}
        toolName={tool}
        open={tool !== null}
        onClose={() => setTool(null)}
        onEditGroup={() => setEditOpen(true)}
      />
      <EditGroupDialog group={group} open={editOpen} onOpenChange={setEditOpen} />
      {group.source ? (
        <ReimportDialog group={group} open={reimportOpen} onOpenChange={setReimportOpen} />
      ) : null}
      <DeleteGroupDialog
        group={group}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={() => navigate("/custom-tools")}
      />
    </div>
  );
}
