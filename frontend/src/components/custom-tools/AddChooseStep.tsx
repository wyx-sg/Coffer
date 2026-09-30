// src/components/custom-tools/AddChooseStep.tsx — step one of Add custom tool: the group first (an existing
// one takes a request by hand; a new one offers Import an OpenAPI spec or a request by hand).
import { useTranslation } from "react-i18next";
import { FileJson, List } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { cn } from "@/lib/utils";
import { NEW_GROUP, type AddWay } from "./addFlow";
import { WayCard } from "./WayCard";

interface Props {
  groups: CustomToolGroup[];
  /** An existing group's name, or NEW_GROUP; "" until one is picked. */
  target: string;
  onTarget: (target: string) => void;
  way: AddWay;
  onWay: (way: AddWay) => void;
  onCancel: () => void;
  onContinue: () => void;
}

function Choice(props: {
  checked: boolean;
  title: string;
  sub: string;
  mono?: boolean;
  onPick: () => void;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-1.5 transition-colors duration-fast",
        props.checked ? "bg-surface-selected" : "hover:bg-surface-hover",
      )}
    >
      <input
        type="radio"
        name="ct-target"
        className="size-4 accent-accent"
        checked={props.checked}
        onChange={props.onPick}
      />
      <span className="min-w-0">
        <span className={cn("block text-sm text-text", props.mono ? "font-mono" : "font-label")}>
          {props.title}
        </span>
        <span className="block text-xs text-text-muted">{props.sub}</span>
      </span>
    </label>
  );
}

export function AddChooseStep({ groups, target, way, ...props }: Props) {
  const { t } = useTranslation();
  const isNew = target === NEW_GROUP;
  const sub = (g: CustomToolGroup) =>
    [
      t(g.source ? "customTools.group.imported" : "customTools.group.byHand"),
      t("customTools.list.toolCount", { count: g.tools.length }),
      g.enabled ? null : t("customTools.tools.off").toLowerCase(),
    ]
      .filter(Boolean)
      .join(" · ");

  return (
    <>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <p id="ct-put-it-in" className="text-xs font-label">
            {t("customTools.add.putItIn")}
          </p>
          <div
            role="radiogroup"
            aria-labelledby="ct-put-it-in"
            className="max-h-72 overflow-y-auto rounded-lg border border-border-subtle p-1"
          >
            {groups.map((g) => (
              <Choice
                key={g.uid}
                mono
                checked={target === g.name}
                title={g.name}
                sub={sub(g)}
                onPick={() => props.onTarget(g.name)}
              />
            ))}
            <Choice
              checked={isNew}
              title={t("customTools.add.newGroup")}
              sub={t("customTools.add.newGroupSub")}
              onPick={() => props.onTarget(NEW_GROUP)}
            />
          </div>
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
        <Button variant="outline" onClick={props.onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={target === ""} onClick={props.onContinue}>
          {t("customTools.add.continue")}
        </Button>
      </DialogFooter>
    </>
  );
}
