// src/components/chat/ReplyParts.tsx — the small parts around an agent reply's
// content: the header's state word ("10:14 · 42s", "Working · 1m 12s", "Stopped
// after 12s", "Failed after 38s"), the "Stopped by you." line, and the footer
// with Copy reply and the token counts.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { elapsedMs, formatDuration } from "@/lib/format/duration";
import { clock } from "@/lib/conversations/time";
import type { UnfinishedWork } from "@/lib/chat/stopped";
import { useNow } from "@/lib/chat/useNow";

/** Where a reply stands. `lost`: the live stream dropped, so the page cannot say. */
export type ReplyState = "done" | "running" | "waiting" | "stopped" | "failed" | "lost";

interface HeaderProps {
  state: ReplyState;
  startedAt?: string;
  finishedAt?: string | null;
}

/** The clock time of a reply and what became of it, after the agent's name. */
export function ReplyStateText({ state, startedAt, finishedAt }: HeaderProps) {
  const { t } = useTranslation();
  const now = useNow(state === "running");
  const ended = elapsedMs(startedAt, finishedAt);
  const sinceStart =
    state === "running" && startedAt ? Math.max(0, now - Date.parse(startedAt)) : null;
  let word: string | null = null;
  if (state === "running") {
    word =
      sinceStart != null && !Number.isNaN(sinceStart)
        ? t("conversations.turn.working", { duration: formatDuration(sinceStart) })
        : t("conversations.turn.workingNoTime");
  } else if (state === "waiting") {
    word = t("conversations.turn.waiting");
  } else if (state === "stopped") {
    word =
      ended != null
        ? t("conversations.turn.stoppedAfter", { duration: formatDuration(ended) })
        : t("conversations.turn.stopped");
  } else if (state === "failed") {
    word =
      ended != null
        ? t("conversations.turn.failedAfter", { duration: formatDuration(ended) })
        : t("conversations.turn.failedWord");
  } else if (state === "done" && ended != null) {
    word = formatDuration(ended);
  }
  const parts = [startedAt ? clock(startedAt) : null, word].filter(Boolean);
  if (parts.length === 0) return null;
  return (
    <time dateTime={startedAt} className="text-2xs text-text-subtle">
      {parts.join(" · ")}
    </time>
  );
}

/** "Stopped by you." plus what a tool still running at the stop left undone. */
export function StoppedLine({ unfinished }: { unfinished: UnfinishedWork | null }) {
  const { t } = useTranslation();
  const rest =
    unfinished === "edit"
      ? ` ${t("conversations.turn.editNotFinished")}`
      : unfinished === "command"
        ? ` ${t("conversations.turn.commandNotFinished")}`
        : "";
  return (
    <p className="text-xs text-text-muted">
      {t("conversations.turn.stoppedByYou")}
      {rest}
    </p>
  );
}

const COPIED_MS = 1500;

/** The end of a finished reply: Copy reply, then the token counts. */
export function ReplyFooter({ text, tokens }: { text: string; tokens: string | null }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(timer);
  }, [copied]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Clipboard unavailable: the text stays selectable by hand.
    }
  };
  if (!text && !tokens) return null;
  return (
    <div className="flex items-center gap-2">
      {text ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("conversations.turn.copyReply")}
                onClick={() => void copy()}
              >
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("conversations.turn.copyReply")}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : null}
      {tokens ? <p className="text-2xs text-text-subtle">{tokens}</p> : null}
    </div>
  );
}
