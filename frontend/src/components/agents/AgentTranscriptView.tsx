// frontend/src/components/agents/AgentTranscriptView.tsx
// The turns of one past conversation (board 2.1.52), rendered as a
// conversation rather than dumped as JSON: one 720 column in a scroller, the
// session's heading on top (`header`), then each turn set apart by who spoke:
// the person's is a right-aligned accent bubble, the same one the Chat page
// uses, and the agent's is unboxed on the left under its mark and name. A turn
// too long to show says so in one quiet line. The raw `.jsonl` is one click away through the viewer
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

import { AgentBadge } from "@/components/agent/AgentBadge";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { TranscriptMessage } from "@/lib/api/agentTranscripts";
import { splitTurnText } from "@/lib/transcriptText";
import { formatDateTime } from "@/lib/utils";

const TIME = (iso: string) => formatDateTime(iso).slice(11, 16);

/** The person's turn: a right-aligned bubble like the Chat page's, so the two
 *  sides of the conversation read apart at a glance. The harness's blocks fold
 *  above it; a turn that was nothing BUT harness stays muted and unbubbled —
 *  a bubble would claim the person said it. */
function UserTurn({ message }: { message: TranscriptMessage }) {
  const { t } = useTranslation();
  const { harness, human } = splitTurnText(message.text);
  const words = human.trim() ? human.trim() : harness ? "" : message.text;

  return (
    <li className="flex flex-col items-end gap-1">
      <span className="sr-only">{t("agents.sessionsTab.roleUser")}</span>
      {harness ? (
        <details className="w-fit max-w-[min(540px,100%)]">
          <summary className="cursor-pointer text-right text-xs text-text-muted">
            {t("agents.sessionsTab.harnessPrefix")}
          </summary>
          <p className="mt-1.5 whitespace-pre-wrap break-words text-xs text-text-muted">
            {harness.trim()}
          </p>
        </details>
      ) : null}
      {words ? (
        <div className="w-fit max-w-[min(540px,100%)] break-words rounded-xl bg-accent-soft px-3.5 py-2.5 text-sm leading-relaxed text-text">
          <p className="whitespace-pre-wrap break-words">{words}</p>
        </div>
      ) : null}
      {message.truncated ? (
        <p className="rounded-lg bg-surface-sunken px-3 py-2 text-xs text-text-muted">
          {t("agents.sessionsTab.turnTruncated")}
        </p>
      ) : null}
      {message.timestamp ? (
        <span className="text-xs text-text-muted">{TIME(message.timestamp)}</span>
      ) : null}
    </li>
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
  if (message.role === "user") return <UserTurn message={message} />;
  // The agent is named; an unrecognised role shows verbatim rather than as a
  // missing-key placeholder, since a future agent format may introduce roles
  // this build has not heard of.
  const label = message.role === "assistant" ? agentName : message.role;
  return (
    <li className="flex gap-3">
      <AgentBadge type={agentType} size="md" tooltip={false} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-text">{label}</span>
          {message.timestamp ? (
            <span className="text-xs text-text-muted">{TIME(message.timestamp)}</span>
          ) : null}
        </div>
        <div className="mt-1 text-sm text-text">
          {/* A reply opening with `---` is prose, not a file's frontmatter. */}
          <FindableMarkdown frontmatter={false}>{message.text}</FindableMarkdown>
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
