// src/components/secret/ApprovalsBatchReview.tsx — the review step and the outcome of a batch.
//
// The review lists EVERY change the confirmation will cover, each as secret →
// destination (slot) and the target that receives it, so what the person
// approves is what is on screen; the shell then reads the same approvals from
// the daemon, names them in its own prompt and signs over exactly that list.
// After the check the same rows show what happened to each: approved, or
// skipped because the target changed or nothing waits for it any more.
import { Check, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import type { Approval, ApprovalBatchResult, SecretRef } from "@/lib/api/secret";
import { displayName } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

interface Props {
  /** Exactly the changes the confirmation covers, as the person saw them. */
  approvals: Approval[];
  rows: SecretRef[];
  /** Set once the check has run: what happened to each id. */
  results: ApprovalBatchResult[] | null;
  busy: boolean;
  onBack: () => void;
  onConfirm: () => void;
  onDone: () => void;
}

export function ApprovalsBatchReview({
  approvals,
  rows,
  results,
  busy,
  onBack,
  onConfirm,
  onDone,
}: Props) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  const outcome = (id: string) => results?.find((r) => r.id === id);

  const line = (a: Approval): { title: string; detail: string | null } => {
    const row = rows.find((r) => r.ref === a.ref);
    const name = row ? displayName(row) : (a.ref ?? "").replace(/^secret\//, "");
    if (a.op !== "bind") {
      return {
        title: t(`secrets.approvals.question.${a.op}`, { name, destination: "" }),
        detail: null,
      };
    }
    const where = [a.destination_kind && kindLabel(a.destination_kind), a.destination_label]
      .filter(Boolean)
      .join(" ");
    return {
      title: `${name} → ${a.slot ? `${where} (${a.slot})` : where}`,
      detail: a.target,
    };
  };

  return (
    <div className="space-y-3" data-testid="approvals-batch-review">
      <p className="flex items-center gap-1.5 text-xs text-text-muted">
        {results
          ? t("secrets.approvals.batch.resultHint")
          : t("secrets.approvals.batch.reviewHint")}
        <HelpTip>{t("secrets.approvals.batch.help")}</HelpTip>
      </p>
      <ul className="max-h-[50vh] space-y-2 overflow-y-auto">
        {approvals.map((a) => {
          const { title, detail } = line(a);
          const done = outcome(a.id);
          const skipped = results !== null && done?.outcome !== "approved";
          return (
            <li
              key={a.id}
              className="flex items-start gap-2 rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2"
              data-testid="batch-review-row"
            >
              {results ? (
                skipped ? (
                  <Minus className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                ) : (
                  <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
                )
              ) : null}
              <div className="min-w-0 space-y-0.5 text-xs">
                <p className="break-all font-medium text-text">{title}</p>
                {detail ? <p className="break-all text-text-muted">{detail}</p> : null}
                {results ? (
                  <p className={skipped ? "text-warning" : "text-text-muted"}>
                    {skipped
                      ? t(`secrets.approvals.batch.skipped.${done?.reason ?? "not_pending"}`)
                      : t("secrets.approvals.batch.approved")}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
      <div className="flex justify-end gap-2">
        {results ? (
          <Button size="sm" onClick={onDone}>
            {t("secrets.approvals.batch.done")}
          </Button>
        ) : (
          <>
            <Button size="sm" variant="outline" disabled={busy} onClick={onBack}>
              {t("secrets.approvals.batch.back")}
            </Button>
            <Button size="sm" disabled={busy} onClick={onConfirm}>
              {t("secrets.approvals.batch.confirm", { count: approvals.length })}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
