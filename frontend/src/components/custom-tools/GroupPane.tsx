// src/components/custom-tools/GroupPane.tsx — the selected group, as one page with no tabs: header,
// secret banner, definition, tools table; the tool drawer, Edit group, Re-import and Delete over it.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Wrench } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { EmptyState } from "@/components/EmptyState";
import { SectionStack } from "@/components/Section";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useCustomToolGroup } from "@/lib/hooks/useCustomTools";
import { DeleteGroupDialog } from "./DeleteGroupDialog";
import { EditGroupDialog } from "./EditGroupDialog";
import { GroupDefinition } from "./GroupDefinition";
import { GroupHeader } from "./GroupHeader";
import { GroupBanners } from "./GroupBanners";
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

  return (
    <div className="space-y-6 px-7 py-6">
      <GroupHeader
        group={group}
        onEdit={() => setEditOpen(true)}
        onDelete={() => setDeleteOpen(true)}
      />
      <GroupBanners group={group} onChooseAnother={() => setEditOpen(true)} />
      <SectionStack>
        <GroupDefinition group={group} onReimport={() => setReimportOpen(true)} />
        <ToolsTable group={group} onOpenTool={setTool} onAddRequest={onAddRequest} />
      </SectionStack>
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
