// frontend/src/components/agents/AgentTranscriptView.test.tsx — a turn leads with the person's words; the harness's blocks fold behind them.
import { describe, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import "@/i18n";
import type { TranscriptMessage } from "@/lib/api/agentTranscripts";
import { acceptance } from "@/test/acceptance";

import { AgentTranscriptView } from "./AgentTranscriptView";

const turn = (text: string): TranscriptMessage =>
  ({ role: "user", text, timestamp: null, truncated: false }) as TranscriptMessage;

describe("AgentTranscriptView", () => {
  acceptance(
    "agent-registry",
    "lead a turn with the person's words, not the harness's blocks",
    () => {
      const reminder = "<system-reminder>Today is Friday.</system-reminder>";
      render(
        <AgentTranscriptView
          agentName="Claude Code"
          agentType="claude_code"
          messages={[
            turn(`${reminder}\nWhy did the build fail?`),
            turn("<task-notification>build finished</task-notification>"),
          ]}
        />,
      );
      // The first turn leads with the question; the reminder is folded behind it, not dropped.
      const question = screen.getByText("Why did the build fail?");
      expect(question.tagName).toBe("P");
      const folded = screen.getByText("<system-reminder>Today is Friday.</system-reminder>");
      expect(folded.closest("details")).not.toBeNull();
      // The turn of only harness blocks renders as harness text, with no empty person's paragraph.
      const only = screen.getByText("<task-notification>build finished</task-notification>");
      expect(only.closest("details")).not.toBeNull();
      expect(screen.getAllByRole("listitem")).toHaveLength(2);
      expect(document.querySelectorAll("li > div > div > p")).toHaveLength(1);
    },
  );
});
