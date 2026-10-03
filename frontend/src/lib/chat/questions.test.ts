import { describe, expect, test } from "vitest";

import type { Question } from "@/lib/api/chat";
import { contentBlock } from "./contentBlock";
import { currentIndex, pendingQuestion, upsertQuestion } from "./questions";

const q = (over: Partial<Question> = {}): Question => ({
  question_id: "q1",
  context: null,
  questions: [
    { header: "a", question: "A?", multi_select: false, options: [] },
    { header: "b", question: "B?", multi_select: false, options: [] },
  ],
  status: "pending",
  answers: [],
  answered_via: null,
  answered_by: null,
  answered_at: null,
  ...over,
});

describe("questions", () => {
  test("upsert replaces a question by its id and appends a new one", () => {
    const text = contentBlock({ type: "text", text: "hi" });
    const first = upsertQuestion([text], q());
    expect(first).toHaveLength(2);
    const next = upsertQuestion(
      first,
      q({ answers: [{ header: "a", selected: ["x"], text: null }] }),
    );
    expect(next).toHaveLength(2);
    expect(next[1].question?.answers).toHaveLength(1);
    expect(upsertQuestion(next, q({ question_id: "q2" }))).toHaveLength(3);
  });

  test("the pending question is the newest one not yet closed", () => {
    const blocks = upsertQuestion([], q({ status: "answered" }));
    expect(pendingQuestion(blocks)).toBeNull();
    expect(pendingQuestion(upsertQuestion(blocks, q({ question_id: "q2" })))?.question_id).toBe(
      "q2",
    );
  });

  test("the current question is as many as are answered", () => {
    expect(currentIndex(q())).toBe(0);
    expect(currentIndex(q({ answers: [{ header: "a", selected: [], text: "x" }] }))).toBe(1);
  });
});
