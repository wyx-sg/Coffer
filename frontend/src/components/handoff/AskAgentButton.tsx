// src/components/handoff/AskAgentButton.tsx — the one hand-off control, [Ask an agent ▾] (Foundations 0.7.04).
//
// A split outline button: the main half opens the draft New conversation with
// the daemon's prompt typed in (nothing is sent until the person presses
// Send); the ▾ half opens a one-item menu, Copy prompt — for an agent outside
// Coffer — which toasts "Prompt copied". With no managed agent only Copy
// prompt is offered, as a plain button. It sits after the problem's own
// buttons (Check again, Retry), never as the page's primary action. Knows
// nothing about the chore: the caller passes the prompt as given.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Copy, MessageSquarePlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useAgentHandoff } from "./useAgentHandoff";

interface Props {
  /** The backend's hand-off text, passed on as is — never assembled by the caller. */
  prompt: string;
  size?: "sm" | "default";
}

export function AskAgentButton({ prompt, size = "sm" }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { copy, canAsk, ask } = useAgentHandoff(prompt);
  const [open, setOpen] = useState(false);
  const copyPrompt = () => {
    copy();
    toast.success(t("handoff.promptCopied"));
  };

  if (!canAsk) {
    return (
      <Button type="button" variant="outline" size={size} onClick={copyPrompt}>
        <Copy aria-hidden /> {t("handoff.copyPrompt")}
      </Button>
    );
  }

  return (
    <div className="inline-flex">
      <Button
        type="button"
        variant="outline"
        size={size}
        className="rounded-r-none"
        onClick={ask}
      >
        <MessageSquarePlus aria-hidden /> {t("handoff.askAgent")}
      </Button>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            aria-label={t("handoff.moreWays")}
            aria-haspopup="menu"
            className={cn(
              "-ml-px rounded-l-none px-0",
              size === "sm" ? "h-control-sm w-6" : "h-control-md w-7",
            )}
          >
            <ChevronDown aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-[260px] p-1">
          <div role="menu" aria-label={t("handoff.moreWays")} className="flex flex-col">
            <button
              type="button"
              role="menuitem"
              autoFocus
              onClick={() => {
                setOpen(false);
                copyPrompt();
              }}
              className="flex w-full gap-2.5 rounded-item px-2.5 py-2 text-left outline-none transition-colors duration-fast hover:bg-surface-hover focus-visible:bg-surface-hover"
            >
              <Copy aria-hidden className="mt-0.5 size-[15px] shrink-0 text-text-subtle" />
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-medium text-text">{t("handoff.copyPrompt")}</span>
                <span className="text-xs text-text-muted">{t("handoff.forOutsideAgent")}</span>
              </span>
            </button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
