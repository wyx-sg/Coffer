// src/components/custom-tools/GroupPane.tsx — the selected group, as one page with no tabs: header,
// secret banner, definition, tools table; the tool drawer, Edit group, Re-import and Delete over it.
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Wrench } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useCustomToolGroup, useDeleteCustomToolGroup } from "@/lib/hooks/useCustomTools";
import type { NewRequestState } from "./AddCustomToolDialog";
import { EditGroupDialog } from "./EditGroupDialog";
import { GroupDefinition } from "./GroupDefinition";
import { GroupHeader } from "./GroupHeader";
import { GroupSecretAlert } from "./GroupSecretAlert";
import { ReimportDialog } from "./ReimportDialog";
import { ToolEditorDrawer } from "./ToolEditorDrawer";
import { ToolsTable } from "./ToolsTable";

interface Props {
  name: string;
}

/** Which tool the drawer shows: a saved one by name, or a new request. */
type Drawer = { tool: string | null } | null;

export function GroupPane({ name }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: group, isPending, error } = useCustomToolGroup(name);
  const del = useDeleteCustomToolGroup(name);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [reimportOpen, setReimportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Arriving from Add custom tool with a request to add: open the drawer,
  // and drop the request from history so Back or a refresh does not reopen it.
  const wantsNew = (location.state as NewRequestState | null)?.newRequest === true;
  useEffect(() => {
    if (!wantsNew || !group) return;
    setDrawer({ tool: null });
    navigate(location.pathname, { replace: true, state: null });
  }, [wantsNew, group, navigate, location.pathname]);

  if (isPending) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
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

  return (
    <div className="space-y-6 p-6">
      <GroupHeader
        group={group}
        onEdit={() => setEditOpen(true)}
        onDelete={() => setDeleteOpen(true)}
      />
      <GroupSecretAlert group={group} onChooseAnother={() => setEditOpen(true)} />
      <GroupDefinition group={group} onReimport={() => setReimportOpen(true)} />
      <ToolsTable
        group={group}
        onOpenTool={(tool) => setDrawer({ tool })}
        onAddRequest={() => setDrawer({ tool: null })}
      />
      <ToolEditorDrawer
        group={group}
        toolName={drawer?.tool ?? null}
        open={drawer !== null}
        onClose={() => setDrawer(null)}
      />
      <EditGroupDialog group={group} open={editOpen} onOpenChange={setEditOpen} />
      {group.source ? (
        <ReimportDialog group={group} open={reimportOpen} onOpenChange={setReimportOpen} />
      ) : null}
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={(next) => {
          setDeleteOpen(next);
          if (!next) del.reset();
        }}
        title={t("customTools.group.deleteTitle", { name: group.name })}
        description={t("customTools.group.deleteBody", { count: group.tools.length })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        error={del.error}
        onConfirm={() =>
          del.mutate(undefined, {
            onSuccess: () => {
              setDeleteOpen(false);
              navigate("/custom-tools");
            },
          })
        }
      />
    </div>
  );
}
