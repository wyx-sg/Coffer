// frontend/src/components/agents/BuiltinAgentTable.tsx — spec 008 US8.
// Lists the built-in agents (kind `builtin_agent`) on the Agents page. Each row
// shows name, model, gateway on/off and a confirm-tools indicator, with row
// actions to edit (opens BuiltinAgentForm) and delete. Delete may 409 with
// CANNOT_DELETE_LAST_BUILTIN_AGENT (the last one is protected); that error is
// shown inside the confirm dialog instead of crashing.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Pencil, ShieldAlert, Trash2, X } from "lucide-react";

import { BuiltinAgentForm } from "@/components/agents/BuiltinAgentForm";
import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { BuiltinAgentOut } from "@/lib/api/builtinAgents";
import { translateApiError } from "@/lib/api/errors";
import { useRemoveBuiltinAgent } from "@/lib/hooks/useBuiltinAgents";

export function BuiltinAgentTable({ agents }: { agents: BuiltinAgentOut[] }) {
  const { t } = useTranslation();
  const remove = useRemoveBuiltinAgent();
  // `null` = closed; otherwise the agent under edit / pending deletion.
  const [editing, setEditing] = useState<BuiltinAgentOut | null>(null);
  const [deleting, setDeleting] = useState<BuiltinAgentOut | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const columns: Column<BuiltinAgentOut>[] = [
    {
      key: "name",
      header: t("builtinAgents.name"),
      className: "whitespace-nowrap",
      cell: (a) => <span className="font-medium">{a.name}</span>,
    },
    {
      key: "model",
      header: t("builtinAgents.model"),
      cell: (a) => <span className="font-mono text-xs">{a.config.model}</span>,
    },
    {
      key: "gateway",
      header: t("builtinAgents.gateway"),
      className: "whitespace-nowrap",
      cell: (a) =>
        a.config.use_gateway !== false ? (
          <Badge variant="secondary" className="gap-1">
            <Check className="size-3" /> {t("builtinAgents.on")}
          </Badge>
        ) : (
          <Badge variant="outline" className="gap-1 text-muted-foreground">
            <X className="size-3" /> {t("builtinAgents.off")}
          </Badge>
        ),
    },
    {
      key: "confirm_tools",
      header: t("builtinAgents.confirm"),
      className: "whitespace-nowrap",
      cell: (a) => {
        const count = a.config.confirm_tools?.length ?? 0;
        return count > 0 ? (
          <Badge variant="outline" className="gap-1">
            <ShieldAlert className="size-3" /> {count}
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        );
      },
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (a) => (
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("builtinAgents.editAria", { name: a.name })}
            onClick={() => setEditing(a)}
          >
            <Pencil className="mr-1.5 size-3.5" /> {t("builtinAgents.edit")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-destructive"
            aria-label={t("builtinAgents.deleteAria", { name: a.name })}
            disabled={remove.isPending}
            onClick={() => {
              setDeleteError(null);
              setDeleting(a);
            }}
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <DataTable
        rows={agents}
        columns={columns}
        rowKey={(a) => a.name}
        search={{
          accessor: (a) => `${a.name} ${a.config.model}`,
          placeholder: t("builtinAgents.searchPlaceholder"),
        }}
        onRowClick={(a) => setEditing(a)}
        emptyMessage={t("builtinAgents.noMatches")}
      />

      {/* Edit dialog. */}
      {editing ? (
        <BuiltinAgentForm
          agent={editing}
          onClose={() => setEditing(null)}
          onSaved={() => setEditing(null)}
        />
      ) : null}

      {/* Delete confirmation — surfaces the last-agent 409 inline. */}
      <Dialog
        open={deleting !== null}
        onOpenChange={(o) => {
          if (!o) {
            setDeleting(null);
            setDeleteError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("builtinAgents.removeConfirm", { name: deleting?.name ?? "" })}
            </DialogTitle>
            <DialogDescription>{t("builtinAgents.removeConfirmBody")}</DialogDescription>
          </DialogHeader>
          {deleteError ? (
            <p className="text-sm text-destructive" role="alert">
              {deleteError}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setDeleting(null);
                setDeleteError(null);
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (!deleting) return;
                remove.mutate(deleting.name, {
                  onSuccess: () => {
                    setDeleting(null);
                    setDeleteError(null);
                  },
                  onError: (err) => setDeleteError(translateApiError(t, err)),
                });
              }}
            >
              {remove.isPending ? t("common.deleting") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
