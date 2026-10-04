// frontend/src/components/skills/SkillChoiceDialog.tsx
// The 1060 "choose which side wins" dialog (canvas 4.3.22 update conflict,
// 4.3.14 file conflict, 4.3.26–4.3.28 a copy that differs): radio cards stacked
// in a 330 column — the chosen one outlined in the accent — with, under them,
// what will happen to each agent, and on the right the diff of the side you are
// NOT keeping. The footer says nothing is written until you choose; its primary
// names the chosen write and changes with the choice.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { agentTypeLabel } from "@/lib/agents/display";
import type { ChangeSummaryLine } from "@/lib/changePreview/changeCounts";
import { cn } from "@/lib/utils";

interface ChoiceCard<T extends string> {
  value: T;
  title: string;
  help: string;
}

interface Props<T extends string> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  subtitle?: ReactNode;
  /** The radiogroup's accessible name. */
  groupLabel: string;
  choices: readonly ChoiceCard<T>[];
  value: T;
  onChange: (value: T) => void;
  /** One sentence per agent, under the cards; omitted for a two-party choice. */
  happen?: readonly ChangeSummaryLine[];
  /** The right column: the diff of the side that is not kept, and its caption. */
  children: ReactNode;
  /** The footer's sentence; defaults to "Nothing is written until you choose." */
  note?: string;
  /** The primary, naming the write the chosen card makes. */
  confirmLabel: string;
  onConfirm: () => void;
  confirmDisabled?: boolean;
  pending?: boolean;
  /** A refusal, kept in the dialog (a DialogErrorBanner); the primary then reads Retry. */
  error?: ReactNode;
}

function Radio({ on }: { on: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "mt-px flex size-4 shrink-0 items-center justify-center rounded-full border",
        on ? "border-transparent bg-accent" : "border-text-subtle bg-surface-raised",
      )}
    >
      {on ? <span className="size-1.5 rounded-full bg-surface-raised" /> : null}
    </span>
  );
}

export function SkillChoiceDialog<T extends string>({
  open,
  onOpenChange,
  title,
  subtitle,
  groupLabel,
  choices,
  value,
  onChange,
  happen,
  children,
  note,
  confirmLabel,
  onConfirm,
  confirmDisabled = false,
  pending = false,
  error,
}: Props<T>) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100vh-4rem)] max-w-[1060px] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-0 pl-5 pr-12 pt-4">
          <DialogTitle>{title}</DialogTitle>
          {subtitle ? <DialogDescription className="text-xs">{subtitle}</DialogDescription> : null}
        </DialogHeader>
        <div className="grid min-h-0 grid-cols-[330px_minmax(0,1fr)] items-start gap-5 overflow-y-auto px-5 pb-[18px] pt-4">
          <div className="flex min-w-0 flex-col gap-3">
            <div role="radiogroup" aria-label={groupLabel} className="flex flex-col gap-2.5">
              {choices.map((c) => {
                const on = c.value === value;
                return (
                  <button
                    key={c.value}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => onChange(c.value)}
                    className={cn(
                      "flex min-w-0 items-start gap-2.5 rounded-lg border bg-surface-raised p-3 text-left",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
                      on ? "border-accent" : "border-border hover:bg-surface-hover",
                    )}
                  >
                    <Radio on={on} />
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="text-sm font-label text-text">{c.title}</span>
                      <span className="text-xs text-text-muted">{c.help}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {happen && happen.length > 0 ? (
              <section className="flex flex-col gap-2 rounded-lg bg-surface-sunken p-3">
                <h3 className="text-2xs font-semibold text-text-subtle">
                  {t("changePreview.whatWillHappen")}
                </h3>
                {happen.map((line, index) => (
                  <p key={`${line.agentType}-${index}`} className="flex items-start gap-2">
                    <AgentBadge
                      type={line.agentType}
                      name={line.agentName}
                      size="sm"
                      className="mt-px shrink-0"
                    />
                    <span className="min-w-0 text-xs leading-[1.45] text-text-muted">
                      <span className="font-label text-text">
                        {line.agentName ?? agentTypeLabel(line.agentType)}.
                      </span>{" "}
                      {line.text}
                    </span>
                  </p>
                ))}
              </section>
            ) : null}
          </div>
          <div className="flex min-w-0 flex-col gap-3.5">{children}</div>
        </div>
        {error ? <div className="mx-5 mb-3 shrink-0">{error}</div> : null}
        <DialogFooter className="m-0 mt-0 flex-row items-center justify-start gap-2 rounded-none px-5 py-3 sm:justify-start">
          <span className="min-w-0 text-xs text-text-muted">{note ?? t("skills.choice.note")}</span>
          <span className="ml-auto flex shrink-0 gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button disabled={confirmDisabled} loading={pending} onClick={onConfirm}>
              {error ? t("common.retry") : confirmLabel}
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
