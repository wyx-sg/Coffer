// frontend/src/components/channel/HandoffSplit.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Copy, MessageSquarePlus } from "lucide-react";

import { useAgentHandoff } from "@/components/handoff/useAgentHandoff";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/** "Ask an agent ▾": open the draft with the daemon's prompt, or copy it from
 *  the menu behind the chevron. With no managed agent to ask, only Copy prompt. */
export function HandoffSplit({ prompt }: { prompt: string }) {
  const { t } = useTranslation();
  const { copy, canAsk, ask } = useAgentHandoff(prompt);
  const [open, setOpen] = useState(false);
  const copyItem = (
    <button
      type="button"
      role="menuitem"
      className="flex h-[30px] w-full items-center gap-2 rounded-md px-2 text-sm text-text hover:bg-surface-hover"
      onClick={() => {
        setOpen(false);
        copy();
      }}
    >
      <Copy className="size-3.5 text-text-muted" aria-hidden />
      {t("handoff.copyPrompt")}
    </button>
  );
  if (!canAsk) {
    return (
      <Button size="sm" variant="outline" onClick={copy}>
        <Copy aria-hidden />
        {t("handoff.copyPrompt")}
      </Button>
    );
  }
  return (
    <span className="inline-flex items-center">
      <Button size="sm" variant="outline" className="rounded-r-none" onClick={ask}>
        <MessageSquarePlus aria-hidden />
        {t("handoff.askAgent")}
      </Button>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            size="sm"
            variant="outline"
            className="-ml-px w-6 rounded-l-none px-0"
            aria-label={t("channels.banner.moreHandoff")}
            aria-haspopup="menu"
          >
            <ChevronDown aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent role="menu" className="w-[180px] p-1">
          {copyItem}
        </PopoverContent>
      </Popover>
    </span>
  );
}
