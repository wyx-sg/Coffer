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
// Whatever is written here is carried on the attempt the task opens with and
// arrives in its brief (FR-029). It is shown back for the same reason it is
// accepted: a queued instruction nobody can see is one the developer will
// write twice.
import { useTranslation } from "react-i18next";
import { MessageSquareDashed } from "lucide-react";

import { Composer } from "@/components/chat/Composer";
import { EmptyState } from "@/components/EmptyState";

interface Props {
  /** What the task has been told so far, or null when nothing has been. */
  instructions: string | null | undefined;
  /** False when another machine advances this run — read-only here (FR-012). */
  ownedHere: boolean;
  onSay: (text: string) => void;
  pending: boolean;
}

export function TaskBrief({ instructions, ownedHere, onSay, pending }: Props) {
  const { t } = useTranslation();

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
          <EmptyState
            icon={MessageSquareDashed}
            title={t("workflow.nodeConversation.notStartedTitle")}
            description={t("workflow.nodeConversation.notStartedBody")}
          />
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
