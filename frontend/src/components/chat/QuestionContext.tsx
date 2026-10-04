// src/components/chat/QuestionContext.tsx — what a reply's question card needs
// from the open conversation: the agent's name, the channel the question was
// also asked in, and how to send an answer. MessageThread provides it; a bubble
// rendered outside a thread gets inert defaults.
import { createContext, useContext } from "react";

import type { QuestionActions } from "@/lib/chat/questions";

export type { QuestionActions };

export const QuestionContext = createContext<QuestionActions>({
  platform: null,
  answer: async () => false,
});

export const useQuestionActions = () => useContext(QuestionContext);
