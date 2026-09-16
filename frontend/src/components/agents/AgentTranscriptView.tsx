// frontend/src/components/agents/AgentTranscriptView.tsx
// The turns of one past conversation, rendered as a conversation rather than
// dumped as JSON. A session IS a dialogue, so showing it as alternating
// role-labelled turns is the reading that costs the reader nothing to do in
// their head; the raw `.jsonl` is still one click away through the page's
// open-in-editor action, for when the records themselves are the question.
//
// Assistant turns go through <FindableMarkdown> — the same renderer the skill
// and memory file previews use — because an agent writes markdown and reading
// its asterisks is nobody's idea of a preview. User turns stay pre-wrapped
// plain text: a prompt is what the person typed, and markdown-rendering it
// would quietly restructure their words.
//
// A user turn also carries whatever its harness prepended — reminders, task
// notifications, environment blocks — and a page asked to read like a real
// back-and-forth cannot open every other turn with eight lines of machinery.
// Those blocks are folded away rather than dropped (`splitTurnText`): the
// reader sees the question, and the record is still one click from complete.
//
// Everything here is already safe by the time it arrives: the server scrubs
// secrets out of every turn and cuts an over-long one before it crosses the
// wire, so this component never has to decide what may be shown.
import { useTranslation } from "react-i18next";

import { turnDomId } from "@/components/agents/AgentTranscriptOutline";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { TranscriptMessage } from "@/lib/api/agentTranscripts";
import { splitTurnText } from "@/lib/transcriptText";
import { cn } from "@/lib/utils";

function UserTurnText({ text }: { text: string }) {
  const { t } = useTranslation();
  const { harness, human } = splitTurnText(text);

  return (
    <>
      {harness ? (
        <details className="mb-2">
          <summary className="cursor-pointer text-xs text-muted-foreground">
            {t("agents.conversationDetail.harnessPrefix")}
          </summary>
          <p className="mt-1.5 whitespace-pre-wrap break-words text-xs text-muted-foreground">
            {harness.trim()}
          </p>
        </details>
      ) : null}
      {/* A turn that was nothing BUT harness still renders its own emptiness
          honestly rather than as a blank card. */}
      {human.trim() ? (
        <p className="whitespace-pre-wrap break-words">{human.trim()}</p>
      ) : harness ? null : (
        <p className="whitespace-pre-wrap break-words">{text}</p>
      )}
    </>
  );
}

function Turn({ message, index }: { message: TranscriptMessage; index: number }) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  // Only the two roles a transcript actually uses get a translated label; an
  // unrecognised one shows verbatim rather than as a missing-key placeholder,
  // since a future agent format may introduce roles this build has not heard of.
  const label = isUser
    ? t("agents.conversationDetail.roleUser")
    : message.role === "assistant"
      ? t("agents.conversationDetail.roleAssistant")
      : message.role;
  return (
    <li className="space-y-1.5 scroll-mt-2" id={turnDomId(index)}>
      <div className="flex items-baseline gap-2">
        <span
          className={cn("text-xs font-medium", isUser ? "text-primary" : "text-muted-foreground")}
        >
          {label}
        </span>
        {message.timestamp ? (
          <span className="text-xs text-muted-foreground">
            {new Date(message.timestamp).toLocaleString()}
          </span>
        ) : null}
      </div>
      <div
        className={cn(
          "rounded border p-3 text-sm",
          isUser ? "border-primary/20 bg-primary/5" : "bg-background",
        )}
      >
        {isUser ? (
          <UserTurnText text={message.text} />
        ) : (
          <FindableMarkdown>{message.text}</FindableMarkdown>
        )}
        {message.truncated ? (
          <p className="mt-2 text-xs text-muted-foreground">
            {t("agents.conversationDetail.turnTruncated")}
          </p>
        ) : null}
      </div>
    </li>
  );
}

export function AgentTranscriptView({ messages }: { messages: TranscriptMessage[] }) {
  const { t } = useTranslation();

  if (messages.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
        {t("agents.conversationDetail.noTurns")}
      </div>
    );
  }

  // A fixed frame the turns scroll inside, not a list the page grows around.
  // A transcript runs to hundreds of turns; letting it set the page's height
  // pushes the header, the actions and the pager off-screen and leaves the
  // reader scrolling a document rather than reading a conversation. The frame
  // is the same height every file pane on this surface uses, so the page is
  // the same size whichever row was opened.
  return (
    <ul
      data-testid="transcript-turns"
      className={cn("space-y-4 rounded-md border bg-background p-4", FILE_PANE_MAX_HEIGHT)}
    >
      {messages.map((message, index) => (
        // Index-keyed on purpose: a turn has no id of its own, and its position
        // in the file IS its identity — the list is append-only and never
        // reordered, so the usual index-key hazard cannot arise here.
        <Turn key={index} index={index} message={message} />
      ))}
    </ul>
  );
}
