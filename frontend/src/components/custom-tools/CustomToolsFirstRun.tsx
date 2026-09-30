// src/components/custom-tools/CustomToolsFirstRun.tsx — the page with no groups yet: what a custom tool is,
// and the two ways to make the first one.
import { useTranslation } from "react-i18next";
import { FileJson, PencilLine, Plus, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AddWay } from "./addFlow";
import { WayCard } from "./WayCard";

interface Props {
  onAdd: (way: AddWay) => void;
}

export function CustomToolsFirstRun({ onAdd }: Props) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-measure flex-col items-center gap-5 px-6 py-12 text-center">
      <span className="inline-flex size-10 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
        <Wrench className="size-5" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="space-y-1">
        <h2 className="text-md font-semibold">{t("customTools.firstRun.title")}</h2>
        <p className="text-sm text-text-muted">{t("customTools.firstRun.body")}</p>
      </div>
      <div className="grid w-full gap-3 text-left sm:grid-cols-2">
        <WayCard
          role="button"
          icon={FileJson}
          title={t("customTools.ways.importTitle")}
          body={t("customTools.firstRun.importBody")}
          points={[t("customTools.firstRun.importPoint")]}
          onSelect={() => onAdd("import")}
        />
        <WayCard
          role="button"
          icon={PencilLine}
          title={t("customTools.ways.handTitle")}
          body={t("customTools.firstRun.handBody")}
          points={[t("customTools.firstRun.handPoint")]}
          onSelect={() => onAdd("hand")}
        />
      </div>
      <Button onClick={() => onAdd("import")}>
        <Plus aria-hidden />
        {t("customTools.add.action")}
      </Button>
    </div>
  );
}
