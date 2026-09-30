// src/components/custom-tools/CustomToolsFirstRun.tsx — the page with no groups yet: what a custom tool is,
// the two ways to make the first group, and Add custom tool.
import { useTranslation } from "react-i18next";
import { FileJson, List, Plus, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { NEW_GROUP, type AddStart } from "./addFlow";
import { WayCard } from "./WayCard";

interface Props {
  onAdd: (start: AddStart) => void;
}

export function CustomToolsFirstRun({ onAdd }: Props) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-[640px] flex-col items-center gap-5 px-6 py-12 text-center">
      <span className="inline-flex size-11 items-center justify-center rounded-xl bg-accent-soft text-accent-text">
        <Wrench className="size-5" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="space-y-1.5">
        <h2 className="text-md font-bold">{t("customTools.firstRun.title")}</h2>
        <p className="text-sm text-text-muted">{t("customTools.firstRun.body")}</p>
      </div>
      <div className="grid w-full gap-3 text-left sm:grid-cols-2">
        <WayCard
          role="button"
          icon={FileJson}
          title={t("customTools.ways.importTitle")}
          body={t("customTools.firstRun.importBody")}
          points={[t("customTools.firstRun.importPoint")]}
          onSelect={() => onAdd({ target: NEW_GROUP, way: "import" })}
        />
        <WayCard
          role="button"
          icon={List}
          title={t("customTools.ways.handTitle")}
          body={t("customTools.firstRun.handBody")}
          points={[t("customTools.firstRun.handPoint")]}
          onSelect={() => onAdd({ target: NEW_GROUP, way: "hand" })}
        />
      </div>
      <Button onClick={() => onAdd({})}>
        <Plus aria-hidden />
        {t("customTools.add.action")}
      </Button>
    </div>
  );
}
