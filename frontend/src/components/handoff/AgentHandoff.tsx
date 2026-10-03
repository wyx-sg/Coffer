// src/components/handoff/AgentHandoff.tsx — hand an environment-dependent chore to an agent.
//
// Coffer does not run open-ended chores (installing, setting up, fixing) on
// this machine itself; it hands the backend's prompt (a `handoff: {prompt}`
// field) to the person's agent, which picks the right way here. One split
// button (Foundations 0.7.04): the main part, Ask an agent, opens the draft
// New conversation with the prompt in its composer (lib/conversations/handoff.ts);
// the ▾ menu holds Copy prompt, for an agent outside Coffer, and a toast says
// "Prompt copied". Nothing is sent until the person presses Send — managed
// agents run with full permissions. With no managed agent available only a
// Copy prompt button is offered. Knows nothing about what the chore is: the
// caller passes the prompt.
import { ChevronDown, Copy, MessageSquarePlus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { useAgentHandoff, type PromptSource } from "./useAgentHandoff";

interface Props {
  /** The backend's hand-off text, passed on as is — never assembled by the caller;
   *  or a request for it, made when the person picks Ask an agent or Copy prompt. */
  prompt: PromptSource;
  size?: "sm" | "default";
}

export function AgentHandoff({ prompt, size = "default" }: Props) {
  const { t } = useTranslation();
  const { copy, canAsk, ask } = useAgentHandoff(prompt);
  const [open, setOpen] = useState(false);
  const small = size === "sm";

  return (
    <div className="inline-flex items-center gap-2">
      {canAsk ? (
        <div className="inline-flex">
          <Button
            type="button"
            variant="outline"
            size={size}
            className="rounded-r-none border-r-0"
            onClick={ask}
          >
            <MessageSquarePlus aria-hidden />
            {t("handoff.askAgent")}
          </Button>
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size={size}
                aria-label={t("handoff.moreOptions")}
                aria-haspopup="menu"
                className={cn("rounded-l-none px-0", small ? "w-6" : "w-7")}
              >
                <ChevronDown aria-hidden className="!size-3" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-[240px] p-1">
              <div role="menu" aria-label={t("handoff.askAgent")}>
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full items-start gap-2.5 rounded-item px-2.5 py-2 text-left hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none"
                  onClick={() => {
                    setOpen(false);
                    copy();
                  }}
                >
                  <Copy aria-hidden className="mt-0.5 size-3.5 shrink-0 text-text-subtle" />
                  <span className="flex flex-col">
                    <span className="text-sm font-medium text-text">{t("handoff.copyPrompt")}</span>
                    <span className="text-xs text-text-muted">{t("handoff.copyPromptHint")}</span>
                  </span>
                </button>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      ) : (
        <Button type="button" variant="outline" size={size} onClick={copy}>
          <Copy aria-hidden />
          {t("handoff.copyPrompt")}
        </Button>
      )}
      <HelpTip>
        <p className="text-xs">{t("handoff.help")}</p>
      </HelpTip>
    </div>
  );
}
