// src/components/custom-tools/ImportReviewStep.tsx — Import step 2 of 2: the group as it will be made, and
// the operations to turn into tools. Nothing is saved until Create group.
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DialogFooter } from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { OpenApiReading } from "@/lib/api/customTools";
import { authLine } from "@/lib/customTools/drafts";
import { changesDataByDefault } from "@/lib/customTools/groups";
import type { GroupDraft } from "./addFlow";
import { DefinitionRow } from "./DefinitionRow";

interface Props {
  group: GroupDraft;
  reading: OpenApiReading;
  picked: string[];
  onPicked: (picked: string[]) => void;
  location: string;
  creating: boolean;
  error: unknown;
  onBack: () => void;
  onCancel: () => void;
  onCreate: () => void;
}

export function ImportReviewStep(props: Props) {
  const { group, reading, picked } = props;
  const { t } = useTranslation();
  const toggle = (key: string, on: boolean) =>
    props.onPicked(on ? [...picked, key] : picked.filter((k) => k !== key));
  const specLabel = [reading.title, reading.version].filter(Boolean).join(" ");

  return (
    <>
      <div className="flex flex-col gap-4">
        <section className="rounded-lg border border-border-subtle">
          <DefinitionRow label={t("customTools.fields.groupName")} value={group.name} mono />
          <DefinitionRow label={t("customTools.fields.baseUrl")} value={group.baseUrl} mono />
          <DefinitionRow
            label={t("customTools.definition.auth")}
            value={
              group.auth.secret
                ? t("customTools.definition.authBound", {
                    line: authLine(group.auth.header, group.auth.prefix),
                    secret: group.auth.secret,
                  })
                : t("customTools.definition.noAuth")
            }
            mono={Boolean(group.auth.secret)}
          />
          <DefinitionRow
            label={t("customTools.definition.spec")}
            value={specLabel ? `${props.location} · ${specLabel}` : props.location}
            mono
          />
          <DefinitionRow
            label={t("customTools.fields.availableTo")}
            value={
              group.agents === null
                ? t("scope.everywhere")
                : t("scope.agentCount", { count: group.agents.length })
            }
          />
        </section>
        <div>
          <p className="mb-2 text-sm font-semibold">
            {t("customTools.import.operations", { count: reading.operations.length })}
          </p>
          <ul className="max-h-72 divide-y divide-border-subtle overflow-y-auto rounded-lg border border-border-subtle">
            {reading.operations.map((op) => {
              const method = op.tool.method ?? "GET";
              return (
                <li key={op.key}>
                  <label className="flex min-h-row cursor-pointer items-center gap-3 px-3 py-1.5 hover:bg-surface-hover">
                    <Checkbox
                      checked={picked.includes(op.key)}
                      aria-label={op.tool.name}
                      onChange={(e) => toggle(op.key, e.target.checked)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-sm">{op.tool.name}</span>
                      <span className="block truncate font-mono text-xs text-text-muted">
                        {method} {op.tool.path}
                      </span>
                    </span>
                    {(op.tool.changes_data ?? changesDataByDefault(method)) ? (
                      <Badge variant="secondary">{t("customTools.tools.changesData")}</Badge>
                    ) : null}
                  </label>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-xs text-text-muted">{t("customTools.import.reviewNote")}</p>
          {reading.warnings.map((warning) => (
            <p key={warning} className="mt-1 text-xs text-warning">
              {warning}
            </p>
          ))}
        </div>
        {props.error ? (
          <div role="alert" className="flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
            <span>{translateApiError(t, props.error)}</span>
          </div>
        ) : null}
      </div>
      <DialogFooter className="sm:justify-between">
        <Button variant="ghost" onClick={props.onBack}>
          {t("customTools.add.back")}
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={props.onCancel}>
            {t("common.cancel")}
          </Button>
          <Button disabled={props.creating || picked.length === 0} onClick={props.onCreate}>
            {t("customTools.import.create", { count: picked.length })}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
