// src/components/custom-tools/ToolEditorDrawer.tsx — one saved tool's editor (4.2.30–33), a 1040 drawer under the
// title bar over the group's page (the address stays `/custom-tools/<group>`): the editor's tabs beside Try it
// (ToolEditorForm); Delete tool (outline danger) · Cancel · Save in the footer. The tool's switch and reach are
// in the table, not here. Nothing is saved until Save. The request help, the group's headers, the preview and the
// test all read ONE environment — the one the test's picker names (useToolEnvironment); picking it saves nothing.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Trash2 } from "lucide-react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { useDeleteCustomTool, useSaveCustomTool } from "@/lib/hooks/useCustomTools";
import { ToolEditorForm } from "./ToolEditorForm";
import { formOf, formReady, toolOf, type ToolForm } from "./toolForm";
import { useToolEnvironment } from "./useToolEnvironment";

interface Props {
  group: CustomToolGroup;
  /** The tool being edited. */
  toolName: string | null;
  open: boolean;
  onClose: () => void;
  /** A timed-out test's Change timeout: close the drawer and open Edit group. */
  onEditGroup: () => void;
}

export function ToolEditorDrawer({ group, toolName, open, onClose, onEditGroup }: Props) {
  const { t } = useTranslation();
  const tool = toolName === null ? null : (group.tools.find((x) => x.name === toolName) ?? null);
  const [form, setForm] = useState<ToolForm>(() => formOf(tool));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const save = useSaveCustomTool(group.name);
  const del = useDeleteCustomTool(group.name);
  const environment = useToolEnvironment(group, open ? toolName : null);
  const shown = environment.shown;
  const several = (group.environments?.length ?? 0) > 1;

  // A different tool starts from what is saved.
  useEffect(() => {
    if (!open) return;
    setForm(formOf(tool));
    save.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the drawer (re)opens
  }, [open, toolName]);

  const onSave = () => save.mutate({ tool: toolName, body: toolOf(form) }, { onSuccess: onClose });

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="max-w-[1040px]">
        <SheetHeader className="border-b-0 pb-2">
          <SheetTitle className="font-mono">{toolName}</SheetTitle>
          <SheetDescription>
            {t("customTools.editor.subtitle", {
              group: group.name,
              name: `${group.name}__${form.name || "…"}`,
            })}
          </SheetDescription>
        </SheetHeader>
        <ToolEditorForm
          form={form}
          onChange={setForm}
          group={group.name}
          nameLocked
          baseUrl={shown?.base_url ?? ""}
          environment={several ? (shown?.name ?? null) : null}
          groupHeaders={shown?.headers ?? []}
          environments={(group.environments ?? []).filter((e) => e.enabled).map((e) => e.name)}
          test={{ saved: group, environment }}
          saveWord="save"
          onChangeTimeout={() => {
            onClose();
            onEditGroup();
          }}
          initialTab="request"
          key={`${toolName ?? ""}-${open}`}
        />
        {save.error ? (
          <div role="alert" className="flex items-start gap-2 px-5 pb-3 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
            <span>{translateApiError(t, save.error)}</span>
          </div>
        ) : null}
        <SheetFooter>
          <Button variant="danger" onClick={() => setConfirmDelete(true)}>
            <Trash2 aria-hidden />
            {t("customTools.editor.delete")}
          </Button>
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button disabled={!formReady(form) || save.isPending} onClick={onSave}>
              {save.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={(next) => {
          setConfirmDelete(next);
          if (!next) del.reset();
        }}
        title={t("customTools.editor.deleteTitle", { name: toolName ?? "" })}
        description={t("customTools.editor.deleteBody")}
        confirmLabel={del.isPending ? t("common.deleting") : t("customTools.editor.delete")}
        pending={del.isPending}
        error={del.error}
        onConfirm={() => {
          if (toolName === null) return;
          del.mutate(toolName, {
            onSuccess: () => {
              setConfirmDelete(false);
              onClose();
            },
          });
        }}
      />
    </Sheet>
  );
}
