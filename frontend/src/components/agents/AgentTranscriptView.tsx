// frontend/src/components/agents/AgentTranscriptView.tsx
// The turns of one past conversation (board 2.1.52), rendered as a
// conversation rather than dumped as JSON: one 720 column in a scroller, the
// session's heading on top (`header`), then each turn as a 24px avatar — the
// person's, or the agent's mark — a bold name with the time beside it, and the
// text under the name. No bubbles and no boxes; a turn too long to show says
// so in one quiet line. The raw `.jsonl` is one click away through the viewer
// toolbar's Open in editor, for when the records themselves are the question.
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
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { User } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { TranscriptMessage } from "@/lib/api/agentTranscripts";
import { splitTurnText } from "@/lib/transcriptText";
import { formatDateTime } from "@/lib/utils";

function UserTurnText({ text }: { text: string }) {
  const { t } = useTranslation();
  const { harness, human } = splitTurnText(text);

  return (
    <>
      {harness ? (
        <details className="mb-2">
          <summary className="cursor-pointer text-xs text-text-muted">
            {t("agents.sessionsTab.harnessPrefix")}
          </summary>
          <p className="mt-1.5 whitespace-pre-wrap break-words text-xs text-text-muted">
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

function Turn({
  message,
  agentName,
  agentType,
}: {
  message: TranscriptMessage;
  agentName: string;
  agentType: string;
}) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  // The person is "You" and the agent is named; an unrecognised role shows
  // verbatim rather than as a missing-key placeholder,
  // since a future agent format may introduce roles this build has not heard of.
  const label = isUser
    ? t("agents.sessionsTab.roleUser")
    : message.role === "assistant"
      ? agentName
      : message.role;
  return (
    <li className="flex gap-3">
      {isUser ? (
        <span
          aria-hidden
          className="inline-flex size-6 shrink-0 items-center justify-center rounded-item bg-chip text-text-muted"
        >
          <User className="size-3.5" strokeWidth={1.75} />
        </span>
      ) : (
        <AgentBadge type={agentType} size="md" tooltip={false} />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-text">{label}</span>
          {message.timestamp ? (
            <span className="text-xs text-text-muted">
              {formatDateTime(message.timestamp).slice(11, 16)}
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-sm text-text">
          {isUser ? (
            <UserTurnText text={message.text} />
          ) : (
            // A reply opening with `---` is prose, not a file's frontmatter.
            <FindableMarkdown frontmatter={false}>{message.text}</FindableMarkdown>
          )}
        </div>
        {message.truncated ? (
          <p className="mt-2 rounded-lg bg-surface-sunken px-3 py-2 text-xs text-text-muted">
            {t("agents.sessionsTab.turnTruncated")}
          </p>
        ) : null}
      </div>
    </li>
  );
}

export function AgentTranscriptView({
  messages,
  agentName,
  agentType,
  header,
}: {
  messages: TranscriptMessage[];
  /** The agent's product name, labelling its turns. */
  agentName: string;
  /** The agent's type, for its mark beside each reply. */
  agentType: string;
  /** The session's heading and meta line, scrolling with the turns. */
  header?: ReactNode;
}) {
  const { t } = useTranslation();

  // A fixed frame the turns scroll inside, not a list the page grows around.
  // A transcript runs to hundreds of turns; letting it set the page's height
  // pushes the header, the toolbar and the pager off-screen and leaves the
  // reader scrolling a document rather than reading a conversation. The frame
  // takes whatever height the surface leaves, so the page is the same size
  // whichever row was opened.
  return (
    <div data-testid="transcript-turns" className="min-h-0 flex-1 overflow-auto px-8 py-6">
      <div className="mx-auto max-w-[720px]">
        {header}
        {messages.length === 0 ? (
          <p className="py-10 text-center text-sm text-text-muted">
            {t("agents.sessionsTab.noTurns")}
          </p>
        ) : (
          <ul className="space-y-5">
            {messages.map((message, index) => (
              // Index-keyed on purpose: a turn has no id of its own, and its
              // position in the file IS its identity — the list is append-only
              // and never reordered, so the usual index-key hazard cannot arise here.
              <Turn key={index} message={message} agentName={agentName} agentType={agentType} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
