// src/components/secret/ScanPreviewStep.tsx — step two of Find plaintext keys: what applying would change.
//
// Read from a dry run, which writes nothing: the secrets that would be added
// and the files whose value would be replaced by its `coffer://secret/<name>`
// reference. Applying runs the real import; a name that already holds a
// different value is skipped with its file untouched, and the dialog then
// lists what was skipped.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusWord } from "@/components/status/StatusWord";
import type { SecretImport } from "@/lib/api/secret";
import { changeCount, shortPath, type ImportPlan } from "./scanPlan";

interface Props {
  plan: ImportPlan;
  applying: boolean;
  onBack: () => void;
  onApply: () => void;
}

function Section({ title, items, tag }: { title: string; items: string[]; tag: string }) {
  return (
    <section className="space-y-1">
      <h3 className="text-xs font-semibold text-text">
        {title} <span className="font-normal text-text-muted">{items.length}</span>
      </h3>
      <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
        {items.map((item) => (
          <li key={item} className="flex items-center gap-3 px-3 py-1.5 text-xs">
            <span className="min-w-0 flex-1 truncate font-mono text-text" title={item}>
              {item}
            </span>
            <span className="shrink-0 text-text-muted">{tag}</span>
          </li>
        ))}
      </ul>
    </section>
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
            files: plan.files.length,
          })}
        </DialogDescription>
      </DialogHeader>
      <div className="max-h-[360px] space-y-3 overflow-y-auto">
        <Section
          title={t("secrets.scan.previewSecrets")}
          items={plan.secrets}
          tag={t("secrets.scan.add")}
        />
        <Section
          title={t("secrets.scan.previewFiles")}
          items={plan.files.map(shortPath)}
          tag={t("secrets.scan.modify")}
        />
      </div>
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

/** What the import did when some findings were skipped: "Moved 2 of 3 keys". */
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
        <DialogDescription>
          {unwritten.length > 0
            ? t("secrets.scan.unwrittenSummary", {
                path: shortPath(unwritten[0].path),
                name: unwritten[0].name ?? "",
                reason: unwritten[0].reason,
              })
            : t("secrets.scan.skippedSummary", { count: result.skipped.length })}
        </DialogDescription>
      </DialogHeader>
      <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
        {result.moved.map((m) => (
          <li key={m.id} className="flex items-center gap-2 px-3 py-2 text-xs">
            <StatusWord tone="ok">{m.name}</StatusWord>
            <span className="min-w-0 flex-1 truncate text-text-muted" title={m.path}>
              {shortPath(m.path)}
            </span>
          </li>
        ))}
        {result.skipped.map((s) => (
          <li key={s.id} className="space-y-0.5 px-3 py-2 text-xs">
            <div className="flex items-center gap-2">
              <StatusWord tone="err">{s.name ?? t("secrets.scan.skipped")}</StatusWord>
              <span className="min-w-0 flex-1 truncate text-text-muted" title={s.path}>
                {shortPath(s.path)} · {t("secrets.scan.notChanged")}
              </span>
            </div>
            <p className="text-text-muted">{s.reason}</p>
          </li>
        ))}
      </ul>
      <DialogFooter className="items-center">
        <span className="mr-auto text-xs text-text-muted">{t("secrets.scan.inActivity")}</span>
        {unwritten.length > 0 ? (
          <Button
            variant="outline"
            disabled={retrying}
            onClick={() => onRetry(unwritten.map((s) => s.id))}
          >
            {t("secrets.scan.tryAgain")}
          </Button>
        ) : null}
        <Button onClick={onClose}>{t("common.done")}</Button>
      </DialogFooter>
    </>
  );
}
