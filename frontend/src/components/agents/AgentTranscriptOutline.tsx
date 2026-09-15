// frontend/src/components/agents/AgentTranscriptOutline.tsx
//
// The contents list beside a conversation: one entry per turn the USER took,
// in order, each jumping the transcript frame to that turn.
//
// Why only the user's turns. A transcript's structure is the questions — the
// replies answer them, and listing both would produce an outline as long as
// the thing it indexes, which indexes nothing. A reader looking for "where did
// I ask about the migration" is looking for something they wrote.
//
// It is the same left-hand column every other detail surface on this page
// carries (a skill's files, a partition's files, a memory store's files), for
// the same reason: the pane on the right is a fixed frame, so something has to
// say what is in it without scrolling through it.
import { useTranslation } from "react-i18next";

import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import type { TranscriptMessage } from "@/lib/api/agentTranscripts";
import { cn } from "@/lib/utils";

/** One line of the outline: which turn it is, and what it says. */
export interface OutlineEntry {
  /** Index into the rendered window — what `turnDomId` is built from. */
  index: number;
  label: string;
}

/** The id a turn carries so the outline can scroll to it. Exported because
 *  both sides must agree and neither owns the other. */
export const turnDomId = (index: number) => `transcript-turn-${index}`;

/**
 * The user's turns, first line each.
 *
 * A prompt can be a thousand lines of pasted context; the outline shows the
 * first non-empty one, which is what the reader would have recognised it by.
 * Empty and whitespace-only turns are dropped — they index nothing.
 */
export function outlineOf(messages: TranscriptMessage[]): OutlineEntry[] {
  const out: OutlineEntry[] = [];
  messages.forEach((message, index) => {
    if (message.role !== "user") return;
    const firstLine = message.text.split("\n").find((line) => line.trim().length > 0);
    if (!firstLine) return;
    out.push({ index, label: firstLine.trim() });
  });
  return out;
}

export function AgentTranscriptOutline({
  messages,
  className,
}: {
  messages: TranscriptMessage[];
  className?: string;
}) {
  const { t } = useTranslation();
  const entries = outlineOf(messages);

  return (
    <div className={cn("space-y-1", className)}>
      <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("agents.conversationDetail.outline")}
      </p>
      {entries.length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">
          {t("agents.conversationDetail.outlineEmpty")}
        </p>
      ) : (
        <ul className={cn("space-y-0.5", FILE_PANE_MAX_HEIGHT)} data-testid="transcript-outline">
          {entries.map((entry) => (
            <li key={entry.index}>
              <button
                type="button"
                className="w-full truncate rounded px-2 py-1 text-left text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                title={entry.label}
                onClick={() => {
                  // `block: "start"` puts the chosen turn at the top of the
                  // frame rather than wherever it happened to fit, so a click
                  // lands the same way every time.
                  document
                    .getElementById(turnDomId(entry.index))
                    ?.scrollIntoView({ block: "start", behavior: "smooth" });
                }}
              >
                {entry.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
