// src/components/custom-tools/AddCustomToolDialog.tsx — the Add custom tool flow. The group comes first: an
// existing one takes a request by hand (its base URL and secret); a new one is named first (New group →
// its first request). Nothing is saved until the last step's button: Create group, or Add to <group>; a
// failure stays in the dialog and the button becomes Retry.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { persistNewSecrets } from "@/components/secret/secretValue";
import { useToast } from "@/components/ui/toast";
import type { CustomToolGroup, CustomToolGroupIn } from "@/lib/api/customTools";
import { translateApiError } from "@/lib/api/errors";
import { resourcesApi } from "@/lib/api/resources";
import { headersIn } from "./headerRows";
import { cn } from "@/lib/utils";
import { useCreateCustomToolGroup, useSaveCustomTool } from "@/lib/hooks/useCustomTools";
import {
  NEW_GROUP,
  newGroupDraft,
  type AddStart,
  type AddStep,
  type GroupDraft,
} from "./addFlow";
import { AddChooseStep } from "./AddChooseStep";
import { AddRequestStep, type RequestGroup } from "./AddRequestStep";
import { NewGroupStep } from "./NewGroupStep";
import { toolOf, type ToolForm } from "./toolForm";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: CustomToolGroup[];
  /** Where the flow opens (a first-run card, a group's Add request). */
  start?: AddStart;
}

export function AddCustomToolDialog({ open, onOpenChange, groups, start }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const create = useCreateCustomToolGroup();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [step, setStep] = useState<AddStep>("choose");
  const [target, setTarget] = useState("");
  const [group, setGroup] = useState<GroupDraft>(newGroupDraft());
  const existing = groups.find((g) => g.name === target) ?? null;
  const addTool = useSaveCustomTool(existing?.name ?? "");

  // Every opening starts over, where the caller asked.
  useEffect(() => {
    if (!open) return;
    setStep(start?.step ?? "choose");
    setTarget(start?.target ?? NEW_GROUP);
    setSaving(false);
    setSaveError(null);
    setGroup(newGroupDraft());
    create.reset();
    addTool.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const openGroup = (name: string) => {
    onOpenChange(false);
    navigate(`/custom-tools/${encodeURIComponent(name)}`);
  };
  const onContinue = () => {
    if (target !== NEW_GROUP) return setStep("request");
    setStep("newGroup");
  };
  // Secrets typed into the headers are written first, then the group; Off is written after it exists.
  const submit = async (build: () => CustomToolGroupIn) => {
    setSaving(true);
    setSaveError(null);
    try {
      await persistNewSecrets(group.headers.map((h) => h.value));
      const made = await create.mutateAsync(build());
      if (group.reach.mode === "disabled") {
        await resourcesApi.disable(made.uid).catch((e) => toast.error(translateApiError(t, e)));
      }
      openGroup(made.name);
    } catch (e) {
      setSaveError(e);
    } finally {
      setSaving(false);
    }
  };
  const groupBody = (): CustomToolGroupIn => ({
    name: group.name,
    description: group.description.trim() || null,
    base_url: group.baseUrl.trim(),
    headers: headersIn(group.headers),
    agents: group.reach.mode === "restricted" ? (group.reach.scope?.agents ?? []) : null,
  });

  const addRequest = (form: ToolForm) => {
    if (existing) {
      setSaveError(null);
      return addTool.mutate(
        { tool: null, body: toolOf(form) },
        { onSuccess: () => openGroup(existing.name) },
      );
    }
    void submit(() => ({ ...groupBody(), tools: [toolOf(form)] }));
  };

  const header = {
    choose: [t("customTools.add.title"), t("customTools.add.subtitle")],
    newGroup: [t("customTools.newGroup.title"), t("customTools.newGroup.subtitle")],
    request: [t("customTools.request.title"), t("customTools.request.subtitle")],
  }[step];
  const cancel = () => onOpenChange(false);
  const backToChoose = () => setStep("choose");
  const requestGroup: RequestGroup | null = existing
    ? { saved: existing }
    : target === NEW_GROUP
      ? { draft: group }
      : null;
  const taken = groups.map((g) => g.name);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "max-h-[90vh] overflow-y-auto",
          step === "request" ? "max-w-[1040px]" : "max-w-[640px]",
        )}
      >
        <DialogHeader>
          <DialogTitle>{header[0]}</DialogTitle>
          <DialogDescription>{header[1]}</DialogDescription>
        </DialogHeader>
        {step === "choose" ? (
          <AddChooseStep
            groups={groups}
            target={target}
            onTarget={setTarget}
            onCancel={cancel}
            onContinue={onContinue}
          />
        ) : step === "newGroup" ? (
          <NewGroupStep
            group={group}
            onGroup={setGroup}
            taken={taken}
            onBack={backToChoose}
            onCancel={cancel}
            onCreate={() => setStep("request")}
          />
        ) : requestGroup ? (
          <AddRequestStep
            group={requestGroup}
            pending={saving || addTool.isPending}
            error={saveError ?? addTool.error}
            onChangeWay={backToChoose}
            onCancel={cancel}
            onAdd={addRequest}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
