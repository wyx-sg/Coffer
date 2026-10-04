// src/components/secret/ScanPreviewStep.tsx — step two of Find plaintext keys: what applying would change.
//
// Read from a dry run, which writes nothing: the secrets that would be added
// and the skill files and servers whose value would be replaced by a reference. Applying runs the real import; a name that already holds a
// different value is skipped with its file untouched, and the dialog then
// lists what was skipped.
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ShowAllRow } from "@/components/LongList";
import { Section, SectionStack } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusWord } from "@/components/status/StatusWord";
import type { SecretImport } from "@/lib/api/secret";
import { useLongList } from "@/components/useLongList";
import { cn } from "@/lib/utils";
import { changeCount, type ImportPlan } from "./scanPlan";

interface Props {
  plan: ImportPlan;
  applying: boolean;
  onBack: () => void;
  onApply: () => void;
}

function PlanList({ title, items, tag }: { title: string; items: string[]; tag: string }) {
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(items, {
    scrollInside: true,
  });
  return (
    <Section title={title} gap="tight">
      <div className="overflow-hidden rounded-lg border border-border-subtle">
        <ul className={cn("divide-y divide-border-subtle", listClassName)}>
          {visible.map((item) => (
            <li key={item} className="flex items-center gap-3 px-3 py-1.5 text-xs">
              <span className="min-w-0 flex-1 truncate font-mono text-text" title={item}>
                {item}
              </span>
              <span className="shrink-0 text-text-muted">{tag}</span>
            </li>
          ))}
        </ul>
        {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
      </div>
    </Section>
  );
}

export function ScanPreviewStep({ plan, applying, onBack, onApply }: Props) {
  const { t } = useTranslation();
  const count = changeCount(plan);
  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("secrets.scan.previewTitle")}</DialogTitle>
        <DialogDescription>
          {t("secrets.scan.previewSummary", {
            secrets: plan.secrets.length,
            targets: plan.targets.length,
          })}
        </DialogDescription>
      </DialogHeader>
      <SectionStack className="max-h-[420px] overflow-y-auto">
        <PlanList
          title={t("secrets.scan.previewSecrets")}
          items={plan.secrets}
          tag={t("secrets.scan.add")}
        />
        <PlanList
          title={t("secrets.scan.previewTargets")}
          items={plan.targets}
          tag={t("secrets.scan.modify")}
        />
      </SectionStack>
      <p className="text-xs text-text-muted">{t("secrets.scan.previewNote")}</p>
      <DialogFooter>
        <Button variant="ghost" disabled={applying} onClick={onBack}>
          {t("secrets.scan.back")}
        </Button>
        <Button disabled={applying || count === 0} onClick={onApply}>
          {applying ? t("secrets.scan.applying") : t("secrets.scan.apply", { count })}
        </Button>
      </DialogFooter>
    </>
  );
}

interface ResultProps {
  result: SecretImport;
  retrying: boolean;
  /** Move these findings again: their values are stored, their files not rewritten. */
  onRetry: (ids: string[]) => void;
  onClose: () => void;
}

/** What the import did when some findings were skipped: "Moved 2 of 3 keys". A key that is stored
 *  but whose file or server could not be rewritten is a warning, not a failure: the secret exists. */
export function ScanResultStep({ result, retrying, onRetry, onClose }: ResultProps) {
  const { t } = useTranslation();
  const total = result.moved.length + result.skipped.length;
  const unwritten = result.skipped.filter((s) => s.stored);
  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {t("secrets.scan.resultTitle", { moved: result.moved.length, count: total })}
        </DialogTitle>
        <DialogDescription className="sr-only">{t("secrets.scan.inActivity")}</DialogDescription>
      </DialogHeader>
      {unwritten.length > 0 ? (
        <div
          className="flex items-start gap-2.5 rounded-lg bg-warning-soft px-3 py-2.5"
          role="alert"
        >
          <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 text-warning" />
          <div className="flex min-w-0 flex-col gap-[3px]">
            <span className="text-sm font-label text-text">
              {t("secrets.scan.unwrittenTitle", { count: unwritten.length })}
            </span>
            <span className="text-xs leading-[1.45] text-text-muted">
              {unwritten.length === 1
                ? t("secrets.scan.unwrittenBody", {
                    reason: unwritten[0].reason,
                    name: unwritten[0].name ?? unwritten[0].resource,
                  })
                : t("secrets.scan.unwrittenBodyMany")}
            </span>
          </div>
        </div>
      ) : null}
      <ul className="divide-y divide-border-subtle rounded-lg border border-border-subtle">
        {result.moved.map((m) => (
          <li key={m.id} className="flex items-center gap-3 px-3 py-2 text-xs">
            <span className="shrink-0 font-mono text-text">{m.name ?? m.ref}</span>
            <span className="min-w-0 flex-1 truncate text-text-muted" title={m.resource}>
              {m.resource}
            </span>
            <StatusWord tone="ok">{t("secrets.scan.moved")}</StatusWord>
          </li>
        ))}
        {result.skipped.map((s) => (
          <li key={s.id} className="space-y-0.5 px-3 py-2 text-xs">
            <div className="flex items-center gap-3">
              <span className="shrink-0 font-mono text-text">
                {s.name ?? t("secrets.scan.skipped")}
              </span>
              <span className="min-w-0 flex-1 truncate text-text-muted" title={s.resource}>
                {s.resource}
              </span>
              <StatusWord tone={s.stored ? "warn" : "err"}>
                {s.stored ? t("secrets.scan.savedNotChanged") : t("secrets.scan.notChanged")}
              </StatusWord>
            </div>
            {s.stored ? null : <p className="text-text-muted">{s.reason}</p>}
          </li>
        ))}
      </ul>
      <DialogFooter className="items-center">
        <span className="mr-auto text-xs text-text-muted">{t("secrets.scan.inActivity")}</span>
        {unwritten.length > 0 ? (
          <>
            <Button
              variant="outline"
              disabled={retrying}
              onClick={() => onRetry(unwritten.map((s) => s.id))}
            >
              {t("secrets.scan.retry")}
            </Button>
          </>
        ) : null}
        <Button onClick={onClose}>{t("common.done")}</Button>
      </DialogFooter>
    </>
  );
}
