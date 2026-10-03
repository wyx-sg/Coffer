// src/lib/chat/questions.ts — a reply's `question` blocks (spec chat "Pause a
// turn on a question for the owner"): which one is pending, which of its several
// questions is current, how an answer reads, and folding a question event into
// the live blocks. Pure.
import type { ContentBlock, Question, QuestionAnswerIn } from "@/lib/api/chat";
import { contentBlock } from "@/lib/chat/contentBlock";

export interface QuestionActions {
  agentName?: string;
  /** The channel's product name for a channel conversation ("SeaTalk"), else null. */
  platform: string | null;
  /** Answer the question's current sub-question; resolves whether it was accepted. */
  answer: (question: Question, answer: QuestionAnswerIn) => Promise<boolean>;
}

/** The question a block carries, if it is a question block. */
function questionOf(block: ContentBlock): Question | null {
  return block.type === "question" ? block.question : null;
}

/** The newest still-pending question among `blocks`, or null. */
export function pendingQuestion(blocks: readonly ContentBlock[]): Question | null {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const q = questionOf(blocks[i]);
    if (q && q.status === "pending") return q;
  }
  return null;
}

/** Which of an ask's questions is up: as many as are answered so far. */
export function currentIndex(q: Question): number {
  return Math.min(q.answers.length, Math.max(q.questions.length - 1, 0));
}

/** The answers of an answered question as one line: labels and typed text, joined. */
export function answerText(q: Question): string {
  const parts = q.answers.map((a) => [...a.selected, ...(a.text ? [a.text] : [])].join(", "));
  return parts.filter(Boolean).join("; ");
}

/**
 * `blocks` with `question` folded in: the block with the same `question_id` is
 * replaced (a several-question ask is sent again as each is answered), else it
 * is appended where the agent asked.
 */
export function upsertQuestion(blocks: ContentBlock[], question: Question): ContentBlock[] {
  const block = contentBlock({ type: "question", question });
  const at = blocks.findIndex((b) => questionOf(b)?.question_id === question.question_id);
  if (at < 0) return [...blocks, block];
  return blocks.map((b, i) => (i === at ? block : b));
}
