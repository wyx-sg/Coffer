// src/lib/hooks/useThreadQuestion.ts — the question an open conversation waits
// on (spec chat "Answer a question in the conversation"): the pending one in
// the live reply, else in a reply the page reloaded into while its turn still
// runs; what its card needs from the thread; and the send that, while one
// waits, answers it with the typed text instead of queueing a message.
import { useCallback, useMemo } from "react";

import type { Conversation, Message } from "@/lib/api/chat";
import { platformName } from "@/lib/chat/mirror";
import { pendingQuestion, type QuestionActions } from "@/lib/chat/questions";
import type { EchoAttachment } from "@/lib/chat/echoes";
import type { LiveMessage } from "@/lib/hooks/chatTurnEvents";
import { useQuestionAnswer } from "@/lib/hooks/useQuestionAnswer";

interface Options {
  conversation: Conversation;
  liveMessage: LiveMessage | null;
  messages: Message[];
  agentLabel?: string;
  onSend: (text: string, attachments?: EchoAttachment[]) => void | Promise<boolean>;
}

export function useThreadQuestion({
  conversation,
  liveMessage,
  messages,
  agentLabel,
  onSend,
}: Options) {
  const waitingQuestion = useMemo(() => {
    if (liveMessage) return pendingQuestion(liveMessage.blocks);
    const last = messages.at(-1);
    return last?.role === "assistant" && last.status === "streaming"
      ? pendingQuestion(last.content)
      : null;
  }, [liveMessage, messages]);
  const answerQuestion = useQuestionAnswer(conversation.id);
  const platform = conversation.channel_binding?.platform ?? null;
  const questionActions = useMemo<QuestionActions>(
    () => ({
      agentName: agentLabel,
      platform: platform ? platformName(platform) : null,
      answer: answerQuestion,
    }),
    [agentLabel, platform, answerQuestion],
  );
  const sendOrAnswer = useCallback(
    (text: string, attachments?: EchoAttachment[]) =>
      waitingQuestion
        ? answerQuestion(waitingQuestion, { selected: [], text })
        : onSend(text, attachments),
    [waitingQuestion, answerQuestion, onSend],
  );
  return { waitingQuestion, questionActions, sendOrAnswer };
}
