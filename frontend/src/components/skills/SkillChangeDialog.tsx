// frontend/src/components/skills/SkillChangeDialog.tsx
// The 1060 review the Skills page shows before it changes a skill folder
// (canvas 4.3.18 Update, 4.3.20 Restore, the Change source preview; Foundations
// 0.7.03): a title and one subtitle line, the change preview — "N changes in
// Coffer", What will happen, the changed files and their diffs — and a footer
// band with one sentence, a ghost Cancel and the primary that names the write.
// A failure the person must handle stays here: the primary becomes Retry.
//
// It composes the change-preview body rather than ChangePreview itself, because
// a skill change has states that one does not: a stage still being made, a
// source that cannot be reached, a source with nothing new.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ChangePreviewBody } from "@/components/change-preview/ChangePreviewBody";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChangeItem, ChangeSummaryLine } from "@/lib/changePreview/changeCounts";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  subtitle?: ReactNode;
  /** The changes; null while the review is still being made. */
  items: ChangeItem[] | null;
  summaries: ChangeSummaryLine[];
  /** Shown in place of the review: a refusal, or "already up to date". */
  notice?: ReactNode;
  /** What the wait says. */
  loadingLabel?: string;
  /** The footer's one sentence. */
  note?: string;
  /** The primary: what it writes, e.g. "Update to f9e8d7c". */
  confirmLabel: string;
  onConfirm: () => void;
  pending?: boolean;
  /** A failed write (a DialogErrorBanner) under the review. */
  error?: ReactNode;
  /** Replaces Cancel/primary with a single Close when there is nothing to confirm. */
  closeOnly?: boolean;
}

export function SkillChangeDialog({
  open,
  onOpenChange,
  title,
  subtitle,
  items,
  summaries,
  notice,
  loadingLabel,
  note,
  confirmLabel,
  onConfirm,
  pending = false,
  error,
  closeOnly = false,
}: Props) {
  const { t } = useTranslation();
  const ready = !notice && items !== null && items.length > 0;
  const close = () => onOpenChange(false);
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="flex max-h-[calc(100vh-4rem)] max-w-[1060px] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-0 pl-5 pr-12 pt-4">
          <DialogTitle>{title}</DialogTitle>
          {subtitle ? <DialogDescription className="text-xs">{subtitle}</DialogDescription> : null}
        </DialogHeader>
        <div className="flex min-h-0 flex-col gap-3.5 overflow-y-auto px-5 pb-[18px] pt-4">
          {notice ? (
            notice
          ) : items === null ? (
            <div className="flex flex-col gap-3" aria-busy="true">
              {loadingLabel ? (
                <span role="status" className="text-sm text-text-muted">
                  {loadingLabel}
                </span>
              ) : null}
              <Skeleton className="h-2.5 w-[70%]" />
              <Skeleton className="h-2.5 w-[48%]" />
              <Skeleton className="h-2.5 w-[62%]" />
            </div>
          ) : (
            <ChangePreviewBody state="ready" items={items} summaries={summaries} />
          )}
          {error}
        </div>
        <DialogFooter className="m-0 mt-0 flex-row items-center justify-start gap-2 rounded-none px-5 py-3 sm:justify-start">
          <span className="min-w-0 text-xs text-text-muted">{ready ? note : null}</span>
          <span className="ml-auto flex shrink-0 gap-2">
            <Button variant={closeOnly ? "outline" : "ghost"} onClick={close}>
              {closeOnly ? t("common.close") : t("common.cancel")}
            </Button>
            {closeOnly ? null : (
              <Button disabled={!ready} loading={pending} onClick={onConfirm}>
                {error ? t("common.retry") : confirmLabel}
              </Button>
            )}
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
