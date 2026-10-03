// src/components/chat/QuestionCard.test.tsx — the question card of a reply and its
// collapsed line (spec chat "Answer a question in the conversation").
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Question } from "@/lib/api/chat";
import { acceptance } from "@/test/acceptance";
import { QuestionCard } from "./QuestionCard";
import { QuestionContext, type QuestionActions } from "./QuestionContext";

const spec = (
  over: Partial<Question["questions"][number]> = {},
): Question["questions"][number] => ({
  header: "Restart",
  question: "Restart the SeaTalk channel now?",
  multi_select: false,
  options: [
    { label: "Yes", description: null },
    { label: "No", description: null },
  ],
  ...over,
});

const question = (over: Partial<Question> = {}): Question => ({
  question_id: "q1",
  context: null,
  questions: [spec()],
  status: "pending",
  answers: [],
  answered_via: null,
  answered_by: null,
  answered_at: null,
  ...over,
});

function renderCard(q: Question, actions: Partial<QuestionActions> = {}) {
  const answer = vi.fn().mockResolvedValue(true);
  const value: QuestionActions = {
    agentName: "Claude Code",
    platform: null,
    answer,
    ...actions,
  };
  render(
    <QuestionContext.Provider value={value}>
      <QuestionCard question={q} />
    </QuestionContext.Provider>,
  );
  return value.answer as ReturnType<typeof vi.fn>;
}

describe("QuestionCard · pending", () => {
  test("a tap on a single-choice option answers at once", async () => {
    const answer = renderCard(question({ context: "Team bot stops for about **5s**." }));
    expect(screen.getByText("Needs you")).toBeInTheDocument();
    expect(screen.getByText("Restart the SeaTalk channel now?")).toBeInTheDocument();
    expect(screen.getByText("Claude Code is waiting for your answer.")).toBeInTheDocument();
    expect(screen.getByText("5s").tagName).toBe("STRONG");
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    await waitFor(() => expect(answer).toHaveBeenCalledTimes(1));
    expect(answer.mock.calls[0][1]).toEqual({ selected: ["Yes"] });
  });

  test("an option's description sits under its label", () => {
    renderCard(
      question({
        questions: [
          spec({
            options: [
              { label: "Now", description: "Bot stops for 5s" },
              { label: "Later", description: null },
            ],
          }),
        ],
      }),
    );
    expect(screen.getByRole("button", { name: /Now/ })).toHaveTextContent("Bot stops for 5s");
  });

  test("a channel conversation says the question was also asked there", () => {
    renderCard(question(), { platform: "SeaTalk" });
    expect(screen.getByText(/Also asked in SeaTalk/)).toBeInTheDocument();
  });

  acceptance("chat", "a multi-select question is answered with Submit", async () => {
    const answer = renderCard(
      question({
        questions: [
          spec({
            multi_select: true,
            options: [
              { label: "Lint", description: null },
              { label: "Tests", description: null },
              { label: "Docs", description: null },
            ],
          }),
        ],
      }),
    );
    const submit = screen.getByRole("button", { name: "Submit" });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Lint" }));
    fireEvent.click(screen.getByRole("button", { name: "Docs" }));
    expect(screen.getByRole("button", { name: "Lint" })).toHaveAttribute("aria-pressed", "true");
    expect(answer).not.toHaveBeenCalled();
    fireEvent.click(submit);
    await waitFor(() => expect(answer).toHaveBeenCalledTimes(1));
    expect(answer.mock.calls[0][1]).toEqual({ selected: ["Lint", "Docs"] });
  });

  test("several questions show the current one and where it is", () => {
    renderCard(
      question({
        questions: [spec({ question: "First?" }), spec({ question: "Second?" })],
        answers: [{ header: "Restart", selected: ["Yes"], text: null }],
      }),
    );
    expect(screen.getByText("Second?")).toBeInTheDocument();
    expect(screen.queryByText("First?")).not.toBeInTheDocument();
    expect(screen.getByText("Question 2 of 2")).toBeInTheDocument();
  });
});

describe("QuestionCard · closed", () => {
  const answered = (over: Partial<Question> = {}) =>
    question({
      status: "answered",
      answers: [{ header: "Restart", selected: ["Yes"], text: null }],
      answered_via: "web",
      answered_at: "2026-10-03T10:16:00",
      ...over,
    });

  test("answered in Coffer is one line with the answer and the time", () => {
    renderCard(answered());
    const line = screen.getByTestId("question-line");
    expect(line).toHaveTextContent("Restart the SeaTalk channel now?");
    expect(line).toHaveTextContent("Answered: Yes · 10:16");
    expect(line).not.toHaveTextContent("in SeaTalk");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("answered in the chat says where", () => {
    renderCard(answered({ answered_via: "channel-uid" }), { platform: "SeaTalk" });
    expect(screen.getByTestId("question-line")).toHaveTextContent("· in SeaTalk");
  });

  test("a typed answer reads as its text", () => {
    renderCard(
      answered({ answers: [{ header: "Restart", selected: [], text: "only on staging" }] }),
    );
    expect(screen.getByTestId("question-line")).toHaveTextContent("Answered: only on staging");
  });

  test("a cancelled question reads as not answered", () => {
    renderCard(question({ status: "cancelled" }));
    expect(screen.getByTestId("question-line")).toHaveTextContent(
      "Restart the SeaTalk channel now? · Not answered",
    );
  });
});
