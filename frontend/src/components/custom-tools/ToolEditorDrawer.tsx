// src/components/custom-tools/ToolEditorDrawer.tsx — one tool's editor, in a drawer over the group's page
// (the address stays `/custom-tools/<group>`): the request, headers, body, arguments, a reach override and
// Test. Also where a hand-made request is added to the group.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Trash2 } from "lucide-react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { useDeleteCustomTool, useSaveCustomTool } from "@/lib/hooks/useCustomTools";
import { DraftReachField } from "./DraftReachField";
import { ToolArgumentsField } from "./ToolArgumentsField";
import { ToolHeadersField } from "./ToolHeadersField";
import { ToolRequestFields } from "./ToolRequestFields";
import { ToolTestSection } from "./ToolTestSection";
import { formOf, formReady, sameReach, toolOf, type ToolForm } from "./toolForm";

interface Props {
  group: CustomToolGroup;
  /** The tool being edited; `null` adds a new request. */
  toolName: string | null;
  open: boolean;
  onClose: () => void;
}

export function ToolEditorDrawer({ group, toolName, open, onClose }: Props) {
  const { t } = useTranslation();
  const tool = toolName === null ? null : (group.tools.find((x) => x.name === toolName) ?? null);
  const [form, setForm] = useState<ToolForm>(() => formOf(tool));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const save = useSaveCustomTool(group.name);
  const del = useDeleteCustomTool(group.name);

  // A different tool (or a new one) starts from what is saved.
  useEffect(() => {
    if (!open) return;
    setForm(formOf(tool));
    save.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the drawer (re)opens
  }, [open, toolName]);

  const isNew = toolName === null;
  const ready = formReady(form);
  const onSave = () => {
    const original = tool?.reach_override ?? null;
    save.mutate(
      {
        tool: toolName,
        body: toolOf(form),
        reach: sameReach(form.reach, original) ? undefined : form.reach,
      },
      { onSuccess: onClose },
    );
  };
  const title = isNew ? t("customTools.editor.newTitle") : form.name || toolName;
  const agentName = `${group.name}__${form.name || "…"}`;

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            {t("customTools.editor.subtitle", { group: group.name, name: agentName })}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="flex flex-col gap-6">
          <ToolRequestFields
            form={form}
            onChange={setForm}
            baseUrl={group.base_url}
            group={group.name}
          />
          <ToolHeadersField
            group={group}
            headers={form.headers}
            onChange={(headers) => setForm({ ...form, headers })}
          />
          <ToolArgumentsField args={form.args} onChange={(args) => setForm({ ...form, args })} />
          <div className="flex flex-col gap-1.5">
            <Label>{t("customTools.fields.availableTo")}</Label>
            <DraftReachField
              value={form.reach}
              onChange={(reach) => setForm({ ...form, reach })}
              defaultLabel={t("customTools.tools.groupDefault")}
              defaultSub={t("customTools.editor.groupDefaultSub")}
            />
          </div>
          <ToolTestSection
            group={group.name}
            secret={group.auth?.secret ?? null}
            args={form.args}
            draft={() => toolOf(form)}
            ready={form.path.trim() !== "" && form.name.trim() !== ""}
          />
          {save.error ? (
            <div role="alert" className="flex items-start gap-2 text-sm text-danger">
              <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
              <span>{translateApiError(t, save.error)}</span>
            </div>
          ) : null}
        </SheetBody>
        <SheetFooter>
          <label className="inline-flex items-center gap-2 text-xs text-text-muted">
            <Switch
              checked={form.enabled}
              aria-label={t("customTools.editor.enabled")}
              onCheckedChange={(enabled) => setForm({ ...form, enabled })}
            />
            {form.enabled ? t("customTools.tools.on") : t("customTools.tools.off")}
          </label>
          {!isNew ? (
            <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
              <Trash2 aria-hidden />
              {t("customTools.editor.delete")}
            </Button>
          ) : null}
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button disabled={!ready || save.isPending} onClick={onSave}>
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
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
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
