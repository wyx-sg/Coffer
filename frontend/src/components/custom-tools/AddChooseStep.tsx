// src/components/custom-tools/AddChooseStep.tsx — step one of Add custom tool: which group, then which way in.
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { FileJson, PencilLine } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { agentPrefix } from "@/lib/customTools/groups";
import { isGroupName } from "@/lib/customTools/drafts";
import type { AddWay } from "./addFlow";
import { FormField } from "./FormField";
import { WayCard } from "./WayCard";

/** The group select's "make a new one" entry. */
export const NEW_GROUP = "__new__";

interface Props {
  groups: string[];
  /** An existing group's name, or NEW_GROUP. */
  target: string;
  onTarget: (target: string) => void;
  newName: string;
  onNewName: (name: string) => void;
  way: AddWay;
  onWay: (way: AddWay) => void;
  onCancel: () => void;
  onContinue: () => void;
}

export function AddChooseStep(props: Props) {
  const { groups, target, newName, way } = props;
  const { t } = useTranslation();
  const id = useId();
  const isNew = target === NEW_GROUP;
  const taken = isNew && groups.includes(newName);
  const nameError =
    isNew && newName !== "" && !isGroupName(newName)
      ? t("customTools.add.nameInvalid")
      : taken
        ? t("customTools.add.nameTaken")
        : undefined;
  const ready = !isNew || (isGroupName(newName) && !taken);
  const importAllowed = isNew;

  return (
    <>
      <div className="flex flex-col gap-4">
        <FormField label={t("customTools.fields.group")} htmlFor={`${id}-group`} required>
          <Select
            value={target}
            onValueChange={(next) => {
              props.onTarget(next);
              if (next !== NEW_GROUP && way === "import") props.onWay("hand");
            }}
          >
            <SelectTrigger id={`${id}-group`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NEW_GROUP}>{t("customTools.add.newGroup")}</SelectItem>
              {groups.map((name) => (
                <SelectItem key={name} value={name} className="font-mono">
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FormField>
        {isNew ? (
          <FormField
            label={t("customTools.fields.groupName")}
            htmlFor={`${id}-name`}
            required
            help={t("customTools.fields.groupNameHelp", {
              prefix: agentPrefix(newName || "name"),
            })}
            error={nameError}
          >
            <Input
              id={`${id}-name`}
              className="font-mono"
              value={newName}
              aria-invalid={nameError ? true : undefined}
              onChange={(e) => props.onNewName(e.target.value.trim())}
            />
          </FormField>
        ) : null}
        <div role="radiogroup" aria-label={t("customTools.add.waysLabel")} className="grid gap-3">
          <WayCard
            icon={FileJson}
            title={t("customTools.ways.importTitle")}
            body={t("customTools.ways.importBody")}
            points={[
              t("customTools.ways.importPoint1"),
              t("customTools.ways.importPoint2"),
              t("customTools.ways.importPoint3"),
            ]}
            selected={way === "import"}
            disabled={!importAllowed}
            disabledNote={t("customTools.ways.importNewOnly")}
            onSelect={() => props.onWay("import")}
          />
          <WayCard
            icon={PencilLine}
            title={t("customTools.ways.handTitle")}
            body={t("customTools.ways.handBody")}
            points={[
              t("customTools.ways.handPoint1"),
              t("customTools.ways.handPoint2"),
              t("customTools.ways.handPoint3"),
            ]}
            selected={way === "hand"}
            onSelect={() => props.onWay("hand")}
          />
        </div>
        <p className="text-xs text-text-muted">{t("customTools.add.footnote")}</p>
      </div>
      <DialogFooter>
        <Button variant="ghost" onClick={props.onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!ready} onClick={props.onContinue}>
          {t("customTools.add.continue")}
        </Button>
      </DialogFooter>
    </>
  );
}
