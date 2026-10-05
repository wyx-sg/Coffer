// src/components/custom-tools/AddChooseStep.tsx — step one of Add custom tool: the group first, from a select
// you can type into (New group by default; an existing one takes a request by hand; a new one offers Import an
// OpenAPI spec or a request by hand).
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { FileJson, List } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { DialogFooter } from "@/components/ui/dialog";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { NEW_GROUP, type AddWay } from "./addFlow";
import { WayCard } from "./WayCard";

interface Props {
  groups: CustomToolGroup[];
  /** An existing group's name, or NEW_GROUP. */
  target: string;
  onTarget: (target: string) => void;
  way: AddWay;
  onWay: (way: AddWay) => void;
  onCancel: () => void;
  onContinue: () => void;
}

export function AddChooseStep({ groups, target, way, ...props }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const isNew = target === NEW_GROUP;
  const sub = (g: CustomToolGroup) =>
    [
      t(g.source ? "customTools.group.imported" : "customTools.group.byHand"),
      t("customTools.list.toolCount", { count: g.tools.length }),
      g.enabled ? null : t("customTools.tools.off").toLowerCase(),
      g.description,
    ]
      .filter(Boolean)
      .join(" · ");
  const options: ComboboxOption[] = [
    {
      value: NEW_GROUP,
      label: t("customTools.add.newGroup"),
      hint: t("customTools.add.newGroupSub"),
    },
    ...groups.map((g) => ({ value: g.name, label: g.name, hint: sub(g) })),
  ];

  return (
    <>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-group`} className="text-xs font-label">
            {t("customTools.add.putItIn")}
          </label>
          <Combobox
            id={`${id}-group`}
            value={target}
            options={options}
            onChange={props.onTarget}
            placeholder={t("customTools.add.newGroup")}
            emptyMessage={t("customTools.add.noGroupMatches")}
          />
        </div>
        {isNew ? (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-label">{t("customTools.add.startNew")}</p>
            <div
              role="radiogroup"
              aria-label={t("customTools.add.waysLabel")}
              className="grid gap-3 sm:grid-cols-2"
            >
              <WayCard
                icon={FileJson}
                title={t("customTools.ways.importTitle")}
                body={t("customTools.ways.importBody")}
                points={[t("customTools.ways.importPoint1"), t("customTools.ways.importPoint2")]}
                selected={way === "import"}
                onSelect={() => props.onWay("import")}
              />
              <WayCard
                icon={List}
                title={t("customTools.ways.handTitle")}
                body={t("customTools.ways.handBody")}
                points={[t("customTools.ways.handPoint1"), t("customTools.ways.handPoint2")]}
                selected={way === "hand"}
                onSelect={() => props.onWay("hand")}
              />
            </div>
          </div>
        ) : target ? (
          <p className="text-xs text-text-muted">
            {t("customTools.add.existingNote", { group: target })}
          </p>
        ) : null}
      </div>
      <DialogFooter>
        <Button variant="ghost" onClick={props.onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={target === ""} onClick={props.onContinue}>
          {t("customTools.add.continue")}
        </Button>
      </DialogFooter>
    </>
  );
}
