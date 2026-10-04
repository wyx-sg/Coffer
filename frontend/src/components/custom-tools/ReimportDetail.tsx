// src/components/custom-tools/ReimportDetail.tsx — the right side of Re-import: the chosen change's spec text.
// A tool the spec changed shows old against new in the shared diff rows; an operation to add shows its text;
// one the spec dropped has none to show, so it says what happens.
import { useTranslation } from "react-i18next";

import { FileDiff } from "@/components/change-preview/FileDiff";
import type { ReimportItem } from "@/lib/customTools/reimport";
import { specDiff } from "@/lib/customTools/specDiff";
import { SpecViewer } from "./SpecViewer";

interface Props {
  item: ReimportItem;
  /** The spec's file name, for the viewer's path. */
  file: string;
}

export function ReimportDetail({ item, file }: Props) {
  const { t } = useTranslation();
  const path = `${file} · ${item.name}`;
  if (item.op === "modify" && item.oldText != null && item.newText != null) {
    const diff = specDiff(item.oldText, item.newText, item.newStart ?? 1);
    return (
      <div className="flex min-w-0 flex-col gap-2">
        <FileDiff
          item={{
            id: item.id,
            agentType: "coffer",
            path,
            op: "modify",
            added: diff.added,
            removed: diff.removed,
            diff: diff.lines,
          }}
        />
        {item.newRequired && item.newRequired.length > 0 ? (
          <p className="text-xs text-text-muted">
            {t("customTools.reimport.afterApply", { names: item.newRequired.join(", ") })}
          </p>
        ) : null}
      </div>
    );
  }
  const text =
    item.op === "add"
      ? item.source
      : item.newText
        ? { text: item.newText, start_line: item.newStart ?? 1 }
        : null;
  if (item.op !== "remove" && text) {
    return (
      <div className="flex min-w-0 flex-col gap-2">
        <SpecViewer path={path} text={text.text} startLine={text.start_line} />
        {item.op === "modify" ? (
          <p className="text-xs text-text-muted">{t("customTools.reimport.noOldText")}</p>
        ) : null}
      </div>
    );
  }
  return (
    <p className="text-xs text-text-muted">
      {t(item.op === "remove" ? "customTools.reimport.gone" : "customTools.import.noSource")}
    </p>
  );
}
