// src/components/chat/QuestionCard.tsx — a question the agent asked the owner,
// drawn in its reply (boards 3.1.10 and 3.1.11). Pending: a "Needs you" card
// with the context, the current question and its options as equal buttons — a
// single-choice tap answers, a multi-select question toggles and sends with
// Submit — and the line saying who waits. Answered or cancelled: one line.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/status/StatusDot";
import type { Question, QuestionAnswerIn } from "@/lib/api/chat";
import { answerText, currentIndex } from "@/lib/chat/questions";
import { clock } from "@/lib/conversations/time";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./MarkdownContent";
import { useQuestionActions } from "./QuestionContext";

/** The first line the owner sees for an ask: its (first) question. */
function lineText(q: Question): string {
  return q.questions[0]?.question ?? "";
}

function PendingCard({ question: q }: { question: Question }) {
  const { t } = useTranslation();
  const { agentName, platform, answer } = useQuestionActions();
  const index = currentIndex(q);
  const spec = q.questions[index];
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  if (!spec) return null;

  const send = async (body: QuestionAnswerIn) => {
    setBusy(true);
    try {
      const accepted = await answer(q, body);
      if (!accepted) setBusy(false);
    } catch {
      setBusy(false);
    }
  };
  const toggle = (label: string) =>
    setPicked((prev) =>
      prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label],
    );
  const hasDescriptions = spec.options.some((o) => o.description);

  return (
    <section
      aria-label={t("conversations.question.needsYou")}
      data-testid="question-card"
      className="flex flex-col gap-2.5 rounded-lg border border-border bg-surface-raised px-3.5 py-3"
    >
      <span className="inline-flex items-center gap-1.5 text-2xs font-semibold text-warning">
        <StatusDot tone="warn" size={6} />
        {t("conversations.question.needsYou")}
        {q.questions.length > 1 ? (
          <span className="ml-1 font-normal text-text-muted">
            {t("conversations.question.progress", {
              current: index + 1,
              total: q.questions.length,
            })}
          </span>
        ) : null}
      </span>
      {q.context ? (
        <div className="text-sm leading-relaxed text-text">
          <MarkdownContent content={q.context} />
        </div>
      ) : null}
      <span className="text-[15px] font-semibold text-text">{spec.question}</span>
      <div className={cn("flex gap-2", hasDescriptions ? "flex-col items-start" : "flex-wrap")}>
        {spec.options.map((o) => {
          const on = picked.includes(o.label);
          return (
            <Button
              key={o.label}
              type="button"
              variant="outline"
              size={o.description ? "default" : "sm"}
              disabled={busy}
              aria-pressed={spec.multi_select ? on : undefined}
              onClick={() =>
                spec.multi_select ? toggle(o.label) : void send({ selected: [o.label] })
              }
              className={cn(
                o.description && "h-auto flex-col items-start gap-0.5 py-1.5 text-left",
                on && "border-accent bg-accent-soft",
              )}
            >
              <span className="inline-flex items-center gap-1.5 text-xs">
                {on ? <Check aria-hidden /> : null}
                {o.label}
              </span>
              {o.description ? (
                <span className="whitespace-normal text-xs font-normal text-text-muted">
                  {o.description}
                </span>
              ) : null}
            </Button>
          );
        })}
      </div>
      {spec.multi_select ? (
        <div>
          <Button
            type="button"
            size="sm"
            disabled={busy || picked.length === 0}
            onClick={() => void send({ selected: picked })}
          >
            {t("conversations.question.submit")}
          </Button>
        </div>
      ) : null}
      <span className="text-xs text-text-muted">
        {t("conversations.question.waitingFor", { agent: agentName ?? "" })}
        {platform ? ` ${t("conversations.question.alsoAsked", { platform })}` : ""}
      </span>
    </section>
  );
}

function ClosedLine({ question: q }: { question: Question }) {
  const { t } = useTranslation();
  const { platform } = useQuestionActions();
  if (q.status === "cancelled") {
    return (
      <p data-testid="question-line" className="truncate text-xs text-text-muted">
        {lineText(q)} · {t("conversations.question.notAnswered")}
      </p>
    );
  }
  const viaChannel = q.answered_via !== null && q.answered_via !== "web";
  const time = q.answered_at ? clock(q.answered_at) : null;
  return (
    <div
      data-testid="question-line"
      className="flex items-center gap-2 rounded-lg border border-border bg-surface-sunken px-3 py-2 text-[13px] text-text-muted"
    >
      <Check className="size-3.5 shrink-0 text-success" strokeWidth={2} aria-hidden />
      <span className="truncate text-text">{lineText(q)}</span>
      <span className="ml-auto whitespace-nowrap text-xs">
        {t("conversations.question.answered")}{" "}
        <b className="font-semibold text-text">{answerText(q)}</b>
        {time ? ` · ${time}` : ""}
        {viaChannel && platform ? ` · ${t("conversations.question.inPlatform", { platform })}` : ""}
      </span>
    </div>
  );
}

export function QuestionCard({ question }: { question: Question }) {
  return question.status === "pending" ? (
    <PendingCard key={`${question.question_id}-${question.answers.length}`} question={question} />
  ) : (
    <ClosedLine question={question} />
  );
}
