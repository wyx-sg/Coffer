// src/components/custom-tools/AddCustomToolDialog.tsx — the Add custom tool flow: the group first (an
// existing one, or a new one named here), then one of two ways in — import an OpenAPI spec (new group
// only) or add one request by hand. A hand-made request opens the tool drawer on the group's page.
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
import type { CustomToolGroupIn } from "@/lib/api/customTools";
import { authBody } from "@/lib/customTools/drafts";
import { useCreateCustomToolGroup } from "@/lib/hooks/useCustomTools";
import {
  newGroupDraft,
  newImportDraft,
  type AddStep,
  type AddWay,
  type GroupDraft,
  type ImportDraft,
} from "./addFlow";
import { AddChooseStep, NEW_GROUP } from "./AddChooseStep";
import { ImportReviewStep } from "./ImportReviewStep";
import { ImportSpecStep } from "./ImportSpecStep";
import { NewGroupStep } from "./NewGroupStep";

/** What a group page's location state asks for: open the new-request drawer. */
export interface NewRequestState {
  newRequest: true;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The names of the groups that exist. */
  groups: string[];
  /** The way to start on (the first-run cards pick one). */
  initialWay?: AddWay;
}

export function AddCustomToolDialog({ open, onOpenChange, groups, initialWay = "import" }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateCustomToolGroup();
  const [step, setStep] = useState<AddStep>("choose");
  const [target, setTarget] = useState(NEW_GROUP);
  const [way, setWay] = useState<AddWay>(initialWay);
  const [group, setGroup] = useState<GroupDraft>(newGroupDraft());
  const [spec, setSpec] = useState<ImportDraft>(newImportDraft());

  // Every opening starts over.
  useEffect(() => {
    if (!open) return;
    setStep("choose");
    setTarget(NEW_GROUP);
    setWay(initialWay);
    setGroup(newGroupDraft());
    setSpec(newImportDraft());
    create.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const openGroup = (name: string, newRequest: boolean) => {
    onOpenChange(false);
    const state: NewRequestState | undefined = newRequest ? { newRequest: true } : undefined;
    navigate(`/custom-tools/${encodeURIComponent(name)}`, { state });
  };

  const onContinue = () => {
    if (target !== NEW_GROUP) return openGroup(target, true);
    setStep(way === "import" ? "importSpec" : "newGroup");
  };

  const submit = (body: CustomToolGroupIn, newRequest: boolean) =>
    create.mutate(body, { onSuccess: (made) => openGroup(made.name, newRequest) });

  const createImported = () => {
    const reading = spec.reading;
    if (!reading) return;
    const tools = reading.operations
      .filter((op) => spec.picked.includes(op.key))
      .map((op) => ({ ...op.tool, enabled: true, operation: op.tool.operation ?? op.key }));
    const skipped = reading.operations
      .filter((op) => !spec.picked.includes(op.key))
      .map((op) => op.key);
    submit(
      {
        name: group.name,
        base_url: group.baseUrl.trim(),
        auth: authBody(group.auth),
        agents: group.agents,
        tools,
        source: {
          kind: reading.source_kind,
          location: reading.location,
          title: reading.title,
          version: reading.version,
          skipped,
        },
      },
      false,
    );
  };

  const createByHand = () =>
    submit(
      {
        name: group.name,
        base_url: group.baseUrl.trim(),
        auth: authBody(group.auth),
        agents: group.agents,
      },
      true,
    );

  const header = {
    choose: [t("customTools.add.title"), t("customTools.add.subtitle")],
    importSpec: [t("customTools.import.title"), t("customTools.import.step1")],
    importReview: [t("customTools.import.title"), t("customTools.import.step2")],
    newGroup: [t("customTools.newGroup.title"), t("customTools.newGroup.subtitle")],
  }[step];
  const cancel = () => onOpenChange(false);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[560px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{header[0]}</DialogTitle>
          <DialogDescription>{header[1]}</DialogDescription>
        </DialogHeader>
        {step === "choose" ? (
          <AddChooseStep
            groups={groups}
            target={target}
            onTarget={setTarget}
            newName={group.name}
            onNewName={(name) => setGroup({ ...group, name })}
            way={way}
            onWay={setWay}
            onCancel={cancel}
            onContinue={onContinue}
          />
        ) : step === "importSpec" ? (
          <ImportSpecStep
            group={group}
            onGroup={setGroup}
            spec={spec}
            onSpec={setSpec}
            taken={groups}
            onCancel={cancel}
            onNext={() => setStep("importReview")}
          />
        ) : step === "importReview" && spec.reading ? (
          <ImportReviewStep
            group={group}
            reading={spec.reading}
            picked={spec.picked}
            onPicked={(picked) => setSpec({ ...spec, picked })}
            location={spec.reading.location}
            creating={create.isPending}
            error={create.error}
            onBack={() => setStep("importSpec")}
            onCancel={cancel}
            onCreate={createImported}
          />
        ) : (
          <NewGroupStep
            group={group}
            onGroup={setGroup}
            taken={groups}
            creating={create.isPending}
            error={create.error}
            onBack={() => setStep("choose")}
            onCancel={cancel}
            onCreate={createByHand}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
