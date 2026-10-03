// src/components/custom-tools/ImportReviewStep.tsx — Import step 2 of 2 (1060): the group as it will be made
// and its tools on the left, the spec text of the chosen operation in the viewer on the right. Only the
// ticked operations become tools; nothing is saved until Create group.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { OpenApiReading } from "@/lib/api/customTools";
import { operationChangesData, type Operation } from "@/lib/customTools/operations";
import { argumentNames } from "@/lib/customTools/schemaArgs";
import type { GroupDraft } from "./addFlow";
import { ReviewGroupPanel } from "./ReviewGroupPanel";
import { SpecViewer } from "./SpecViewer";

interface Props {
  group: GroupDraft;
  reading: OpenApiReading;
  picked: string[];
  creating: boolean;
  error: unknown;
  onBack: () => void;
  onCancel: () => void;
  onCreate: () => void;
}

/** "GET /invoices/{id} · 1 argument, id · reads data". */
function OperationMeta({ op }: { op: Operation }) {
  const { t } = useTranslation();
  const names = argumentNames(op.tool.input_schema ?? {});
  const args =
    names.length === 0
      ? t("customTools.import.noArguments")
      : t("customTools.import.arguments", { count: names.length, names: names.join(", ") });
  const effect = t(
    operationChangesData(op) ? "customTools.import.changes" : "customTools.import.reads",
  );
  return (
    <span className="text-xs text-text-muted">
      {op.tool.method ?? "GET"} {op.tool.path} · {args} · {effect}
    </span>
  );
}

export function ImportReviewStep(props: Props) {
  const { group, reading, picked } = props;
  const { t } = useTranslation();
  const tools = reading.operations.filter((op) => picked.includes(op.key));
  const skipped = reading.operations
    .filter((op) => !picked.includes(op.key))
    .sort((a, b) => Number(operationChangesData(b)) - Number(operationChangesData(a)));
  const [chosen, setChosen] = useState<string | null>(null);
  const open = reading.operations.find((op) => op.key === chosen) ?? tools[0] ?? skipped[0] ?? null;
  const file = reading.location.split("/").pop() || reading.location;

  return (
    <>
      <div className="grid min-h-0 grid-cols-[340px_minmax(0,1fr)] gap-4">
        <div className="flex max-h-[60vh] min-h-0 flex-col">
          <ReviewGroupPanel
            group={group}
            tools={tools}
            skipped={skipped}
            selected={open?.key ?? null}
            onSelect={setChosen}
          />
        </div>
        <div className="flex max-h-[60vh] min-w-0 flex-col gap-2 overflow-y-auto">
          {open ? (
            <>
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate font-mono text-sm">{`${group.name}__${open.tool.name}`}</span>
                <OperationMeta op={open} />
              </div>
              {open.source ? (
                <SpecViewer
                  path={`${file} · ${open.key}`}
                  text={open.source.text}
                  startLine={open.source.start_line}
                />
              ) : (
                <p className="text-xs text-text-muted">{t("customTools.import.noSource")}</p>
              )}
            </>
          ) : null}
        </div>
      </div>
      {props.error ? (
        <div role="alert" className="flex items-start gap-2 text-sm text-danger">
          <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
          <span>{translateApiError(t, props.error)}</span>
        </div>
      ) : null}
      <DialogFooter className="sm:justify-between">
        <Button variant="outline" onClick={props.onBack}>
          {t("customTools.add.back")}
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={props.onCancel}>
            {t("common.cancel")}
          </Button>
          <Button disabled={props.creating || tools.length === 0} onClick={props.onCreate}>
            {props.error
              ? t("common.retry")
              : t("customTools.import.create", { count: tools.length })}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
