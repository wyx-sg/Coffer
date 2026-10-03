// src/lib/hooks/useQuestionAnswer.ts — send the owner's answer to a pending
// question (spec chat "Answer a question in the conversation"). The answer
// lands on the question's current sub-question; the card follows the
// `question_*` events. A question that closed meanwhile (409 QUESTION_CLOSED —
// answered in the chat, or the turn ended) just refetches and shows its closed
// line; any other failure is a toast.
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { chatApi, type Question, type QuestionAnswerIn } from "@/lib/api/chat";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { conversationHeadsKey, messagesKey, needsYouCountKey } from "@/lib/api/queryKeys";
import { currentIndex } from "@/lib/chat/questions";
import { useToast } from "@/components/ui/toast";

export function useQuestionAnswer(conversationId: string) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { t } = useTranslation();
  return useCallback(
    async (question: Question, answer: QuestionAnswerIn): Promise<boolean> => {
      const refresh = () => {
        void qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
        void qc.invalidateQueries({ queryKey: needsYouCountKey });
        void qc.invalidateQueries({ queryKey: conversationHeadsKey });
      };
      try {
        await chatApi.answerQuestion(
          conversationId,
          question.question_id,
          [answer],
          currentIndex(question),
        );
        refresh();
        return true;
      } catch (err) {
        if (err instanceof ApiError && err.code === "QUESTION_CLOSED") refresh();
        else toast.error(translateApiError(t, err));
        return false;
      }
    },
    [conversationId, qc, t, toast],
  );
}
