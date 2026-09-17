// frontend/src/components/workflow/TaskBrief.tsx
// A task the run has not reached yet — and the composer that briefs it
// (FR-068).
//
// It is NOT a thread pretending to be empty. A task with no conversation has
// said nothing and been told nothing by an agent, and rendering an empty
// transcript would read as a conversation in which nobody spoke. What it can
// have is a BRIEF: what the developer wants it to do when the run gets there,
// written now, while they are thinking about it rather than at 2am when the
// run reaches it.
//
// Two tasks have no conversation and they are not the same. One has not
// started. The other is MANUAL and has: a person is doing it, and there is no
// agent to hold a conversation with, so what is written here joins its
// instructions rather than reaching an agent.
//
// Whatever is written here is carried on the attempt the task opens with and
// arrives in its brief (FR-029). It is shown back for the same reason it is
// accepted: a queued instruction nobody can see is one the developer will
// write twice.
import { useTranslation } from "react-i18next";

import { Composer } from "@/components/chat/Composer";

interface Props {
  /** What the task has been told so far, or null when nothing has been. */
  instructions: string | null | undefined;
  /**
   * False only while the task has never run. A MANUAL task lands here too and
   * is not the same thing: it HAS run — a person is doing it — and it will
   * never have a conversation, because there is no agent to hold one.
   */
  started: boolean;
  /** False when another machine advances this run — read-only here (FR-012). */
  ownedHere: boolean;
  onSay: (text: string) => void;
  pending: boolean;
}

export function TaskBrief({ instructions, started, ownedHere, onSay, pending }: Props) {
  const { t } = useTranslation();
  const key = started ? "byHand" : "notStarted";

  return (
    <section
      className="flex h-full min-h-0 flex-col rounded-lg border border-border bg-card"
      aria-label={t("workflow.brief.label")}
    >
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {instructions ? (
          <div className="space-y-2">
            <h3 className="text-sm font-medium">{t("workflow.brief.queuedTitle")}</h3>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{instructions}</p>
          </div>
        ) : (
          // The same plain paragraph an empty thread uses, and for the same
          // reason: this panel and that one are two states of one place, and a
          // bordered empty-state card here would make them look like two.
          <div className="space-y-1">
            <p className="text-sm font-medium">{t(`workflow.nodeConversation.${key}Title`)}</p>
            <p className="text-sm text-muted-foreground">
              {t(`workflow.nodeConversation.${key}Body`)}
            </p>
          </div>
        )}
      </div>

      <div className="border-t border-border p-3">
        {ownedHere ? (
          <Composer onSend={onSay} disabled={pending} />
        ) : (
          <p className="text-sm text-muted-foreground">{t("workflow.nodeConversation.readOnly")}</p>
        )}
      </div>
    </section>
  );
}
