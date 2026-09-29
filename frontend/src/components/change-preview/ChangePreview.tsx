// src/components/change-preview/ChangePreview.tsx
// The one preview Coffer shows before it writes into agents' files: a 1060 dialog that switches on the write's state.
import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ChangePreviewBody } from "./ChangePreviewBody";
import {
  applyingPosition,
  failedIds,
  type ChangeItem,
  type ChangePreviewState,
  type ChangeSummaryLine,
} from "./changeCounts";

export type { ChangeItem, ChangePreviewState } from "./changeCounts";

interface ChangePreviewProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  /** Title while reviewing, e.g. "Review changes"; applying / applied / failed name themselves. */
  title: string;
  /** What the write is for, e.g. "Reconnect agents to Coffer". */
  subtitle?: string;
  state: ChangePreviewState;
  items: ChangeItem[];
  /** The "What will happen" sentences, one per agent. */
  summaries?: ChangeSummaryLine[];
  onApply(): void;
  /** Called with only the failed ids; applied ones are not rewritten. */
  onRetry?(failedIds: string[]): void;
  /** "View in Activity" on the applied state. */
  activityHref?: string;
}

const NO_SUMMARIES: ChangeSummaryLine[] = [];

function Footer({ note, children }: { note?: string; children: React.ReactNode }) {
  return (
    <DialogFooter className="m-0 mt-0 flex-row items-center justify-start gap-2 rounded-none px-5 py-3 sm:justify-start">
      <span className="min-w-0 text-xs text-text-muted">{note}</span>
      <span className="ml-auto flex shrink-0 gap-2">{children}</span>
    </DialogFooter>
  );
}

export function ChangePreview({
  open,
  onOpenChange,
  title,
  subtitle,
  state,
  items,
  summaries = NO_SUMMARIES,
  onApply,
  onRetry,
  activityHref,
}: ChangePreviewProps) {
  const { t } = useTranslation();
  const locked = state === "applying";
  const close = () => onOpenChange(false);
  const failed = failedIds(items);

  const heading =
    state === "applying"
      ? t("changePreview.applying.title")
      : state === "applied"
        ? t("changePreview.applied.title")
        : state === "failed"
          ? t("changePreview.failed.title")
          : title;

  const cancel = (
    <Button variant="outline" onClick={close} disabled={locked}>
      {t("common.cancel")}
    </Button>
  );

  let footer: React.ReactNode;
  switch (state) {
    case "computing":
      footer = (
        <Footer>
          {cancel}
          <Button disabled>{t("changePreview.apply")}</Button>
        </Footer>
      );
      break;
    case "empty":
      footer = (
        <Footer note={t("changePreview.empty.checked")}>
          <Button variant="outline" onClick={close}>
            {t("common.done")}
          </Button>
        </Footer>
      );
      break;
    case "ready":
      footer = (
        <Footer note={t("changePreview.reassurance")}>
          {cancel}
          <Button onClick={onApply} disabled={items.length === 0}>
            {t("changePreview.applyCount", { count: items.length })}
          </Button>
        </Footer>
      );
      break;
    case "applying":
      footer = (
        <Footer
          note={t("changePreview.applying.progress", {
            current: applyingPosition(items),
            total: items.length,
          })}
        >
          {cancel}
          <Button disabled>{t("changePreview.applyCount", { count: items.length })}</Button>
        </Footer>
      );
      break;
    case "applied":
      footer = (
        <Footer note={t("changePreview.applied.recorded")}>
          {activityHref ? (
            <Button variant="ghost" asChild>
              <a href={activityHref}>{t("changePreview.applied.viewActivity")}</a>
            </Button>
          ) : null}
          <Button onClick={close}>{t("common.done")}</Button>
        </Footer>
      );
      break;
    case "failed":
      footer = (
        <Footer>
          <Button variant="outline" onClick={close}>
            {t("common.close")}
          </Button>
          <Button onClick={() => onRetry?.(failed)} disabled={!onRetry || failed.length === 0}>
            <RotateCcw aria-hidden />
            {t("changePreview.failed.retry", { count: failed.length })}
          </Button>
        </Footer>
      );
      break;
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // While writing, the dialog cannot be dismissed.
        if (!next && locked) return;
        onOpenChange(next);
      }}
    >
      <DialogContent
        data-state-kind={state}
        // The close button is gone while writing.
        hideClose={locked}
        className="flex max-h-[calc(100vh-4rem)] max-w-[1060px] flex-col gap-0 overflow-hidden p-0"
        onEscapeKeyDown={(event) => locked && event.preventDefault()}
        onInteractOutside={(event) => locked && event.preventDefault()}
      >
        <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-0 pl-5 pr-12 pt-4">
          <DialogTitle>{heading}</DialogTitle>
          {subtitle ? <DialogDescription className="text-xs">{subtitle}</DialogDescription> : null}
        </DialogHeader>
        <div className="flex min-h-0 flex-col gap-3.5 overflow-y-auto px-5 pb-[18px] pt-4">
          <ChangePreviewBody state={state} items={items} summaries={summaries} />
        </div>
        {footer}
      </DialogContent>
    </Dialog>
  );
}
