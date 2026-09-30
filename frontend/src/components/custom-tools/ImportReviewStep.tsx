// src/components/custom-tools/ImportReviewStep.tsx — Import step 2 of 2: the group as it will be made, the
// ticked operations that become its tools, and the rest listed as Skipped. Nothing is saved until
// Create group.
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { OpenApiReading } from "@/lib/api/customTools";
import { operationChangesData, type Operation } from "@/lib/customTools/operations";
import type { GroupDraft } from "./addFlow";
import { AuthLine } from "./AuthLine";
import { DefinitionRow } from "./DefinitionRow";
import { DraftReachField } from "./DraftReachField";

/** How many skipped operations are named before "and N more". */
const SKIPPED_SHOWN = 4;

interface Props {
  group: GroupDraft;
  onGroup: (group: GroupDraft) => void;
  reading: OpenApiReading;
  picked: string[];
  creating: boolean;
  error: unknown;
  onBack: () => void;
  onCancel: () => void;
  onCreate: () => void;
}

function OpRow({ op, skipped }: { op: Operation; skipped?: boolean }) {
  const { t } = useTranslation();
  return (
    <li className="grid min-h-9 grid-cols-[minmax(0,1fr)_minmax(0,1fr)_96px] items-center gap-3 border-t border-border-subtle px-3 first:border-t-0">
      <span className={`truncate font-mono text-xs ${skipped ? "text-text-muted" : "text-text"}`}>
        {op.tool.name}
      </span>
      <span className="truncate font-mono text-xs text-text-muted">
        {op.tool.method ?? "GET"} {op.tool.path}
      </span>
      {skipped && operationChangesData(op) ? (
        <Badge variant="warning">{t("customTools.tools.changesData")}</Badge>
      ) : (
        <span />
      )}
    </li>
  );
}

export function ImportReviewStep(props: Props) {
  const { group, reading, picked } = props;
  const { t } = useTranslation();
  const tools = reading.operations.filter((op) => picked.includes(op.key));
  const skipped = reading.operations
    .filter((op) => !picked.includes(op.key))
    .sort((a, b) => Number(operationChangesData(b)) - Number(operationChangesData(a)));
  const specLabel = [reading.title, reading.version].filter(Boolean).join(" ");

  return (
    <>
      <div className="flex flex-col gap-4">
        <section aria-label={t("customTools.import.groupTitle")} className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold">{t("customTools.import.groupTitle")}</h3>
          <div>
            <DefinitionRow
              label={t("customTools.import.name")}
              value={group.name}
              mono
              copyable={false}
            />
            <DefinitionRow label={t("customTools.fields.baseUrl")} value={group.baseUrl} mono />
            <DefinitionRow
              label={t("customTools.definition.auth")}
              value={group.auth.secret ?? ""}
              copyable={false}
            >
              {group.auth.secret ? (
                <AuthLine
                  header={group.auth.header}
                  prefix={group.auth.prefix}
                  secret={group.auth.secret}
                />
              ) : (
                t("customTools.definition.noAuth")
              )}
            </DefinitionRow>
            <DefinitionRow
              label={t("customTools.definition.spec")}
              value={reading.location}
              mono
              copyable={false}
              trailing={
                specLabel ? (
                  <span className="shrink-0 text-xs text-text-muted">{specLabel}</span>
                ) : null
              }
            />
            <div className="flex min-h-row items-center gap-3">
              <span className="w-32 shrink-0 text-xs text-text-muted">
                {t("customTools.fields.availableTo")}
              </span>
              <DraftReachField
                value={group.agents}
                onChange={(agents) => props.onGroup({ ...group, agents })}
              />
            </div>
          </div>
        </section>
        <section aria-label={t("customTools.list.toolCount", { count: tools.length })}>
          <h3 className="mb-1.5 text-sm font-semibold">
            {t("customTools.list.toolCount", { count: tools.length })}
          </h3>
          <ul className="rounded-lg border border-border-subtle">
            {tools.map((op) => (
              <OpRow key={op.key} op={op} />
            ))}
          </ul>
        </section>
        {skipped.length > 0 ? (
          <section aria-label={t("customTools.import.skipped", { count: skipped.length })}>
            <h3 className="mb-1.5 text-sm font-semibold">
              {t("customTools.import.skipped", { count: skipped.length })}
            </h3>
            <ul className="rounded-lg border border-border-subtle">
              {skipped.slice(0, SKIPPED_SHOWN).map((op) => (
                <OpRow key={op.key} op={op} skipped />
              ))}
              {skipped.length > SKIPPED_SHOWN ? (
                <li className="border-t border-border-subtle px-3 py-2 text-xs text-text-muted">
                  {t("customTools.import.moreSkipped", { count: skipped.length - SKIPPED_SHOWN })}
                </li>
              ) : null}
            </ul>
          </section>
        ) : null}
        <p className="text-xs text-text-muted">{t("customTools.import.reviewNote")}</p>
        {props.error ? (
          <div role="alert" className="flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
            <span>{translateApiError(t, props.error)}</span>
          </div>
        ) : null}
      </div>
      <DialogFooter className="sm:justify-between">
        <Button variant="outline" onClick={props.onBack}>
          {t("customTools.add.back")}
        </Button>
        <div className="flex gap-2">
          <Button variant="outline" onClick={props.onCancel}>
            {t("common.cancel")}
          </Button>
          <Button disabled={props.creating || tools.length === 0} onClick={props.onCreate}>
            {t("customTools.import.create", { count: tools.length })}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
