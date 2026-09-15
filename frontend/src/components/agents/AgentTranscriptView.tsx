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
// Everything here is already safe by the time it arrives: the server scrubs
// secrets out of every turn and cuts an over-long one before it crosses the
// wire, so this component never has to decide what may be shown.
import { useTranslation } from "react-i18next";

import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { TranscriptMessage } from "@/lib/api/agentTranscripts";
import { cn } from "@/lib/utils";

function Turn({ message }: { message: TranscriptMessage }) {
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
    <li className="space-y-1.5">
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
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
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

  return (
    <ul className="space-y-4">
      {messages.map((message, index) => (
        // Index-keyed on purpose: a turn has no id of its own, and its position
        // in the file IS its identity — the list is append-only and never
        // reordered, so the usual index-key hazard cannot arise here.
        <Turn key={index} message={message} />
      ))}
    </ul>
  );
}
