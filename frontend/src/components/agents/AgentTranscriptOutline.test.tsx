// The conversation's contents list: the user's turns, in order, each jumping
// the frame to that turn.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import {
  AgentTranscriptOutline,
  outlineOf,
  turnDomId,
} from "@/components/agents/AgentTranscriptOutline";
import type { TranscriptMessage } from "@/lib/api/agentTranscripts";

function turn(role: string, text: string): TranscriptMessage {
  return { role, text, timestamp: null, truncated: false };
}

describe("outlineOf", () => {
  test("indexes the user's turns and nothing else", () => {
    // The replies answer the questions; listing both makes an outline as long
    // as the thing it indexes, which indexes nothing.
    const messages = [
      turn("user", "fix the migration"),
      turn("assistant", "Done — here is what changed."),
      turn("user", "now ship it"),
    ];

    expect(outlineOf(messages)).toEqual([
      { index: 0, label: "fix the migration" },
      { index: 2, label: "now ship it" },
    ]);
  });

  test("shows a long prompt by its first line", () => {
    // A prompt can be a thousand lines of pasted context; the first line is
    // what the reader would recognise it by.
    const messages = [turn("user", "rename the column\n\n```sql\nALTER TABLE …\n```")];

    expect(outlineOf(messages)[0].label).toBe("rename the column");
  });

  test("skips a turn that is only whitespace", () => {
    // It indexes nothing, and an empty row in a contents list is worse than a
    // shorter list.
    expect(outlineOf([turn("user", "   \n\n ")])).toEqual([]);
  });

  test("indexes a turn by the question, not by the reminder in front of it", () => {
    // What made the list useless on a real transcript: twelve of its fifteen
    // entries read `<task-notification>`, because the harness prepends its
    // blocks to the same turn the person typed into.
    const messages = [
      turn(
        "user",
        "<system-reminder>\nYou are operating in a git worktree.\n</system-reminder>\n\n" +
          "only show whether it is installed",
      ),
    ];

    expect(outlineOf(messages)).toEqual([
      { index: 0, label: "only show whether it is installed" },
    ]);
  });

  test("drops a turn the person did not write at all", () => {
    // A notification the harness delivered into the transcript is not a
    // question anybody is scanning the contents list to find again.
    const messages = [
      turn("user", "<task-notification>\nbuild finished\n</task-notification>"),
      turn("user", "ship it"),
    ];

    expect(outlineOf(messages)).toEqual([{ index: 1, label: "ship it" }]);
  });

  test("prose that merely contains an angle bracket is left alone", () => {
    // The rule is the tag SHAPE, not a list of names — and a comparison is not
    // a tag, however much it looks like the start of one.
    expect(outlineOf([turn("user", "assert a < b for every row")])[0].label).toBe(
      "assert a < b for every row",
    );
  });

  test("the index is the turn's position in the window, not among the prompts", () => {
    // It is what `turnDomId` is built from, so an outline counting only its
    // own entries would scroll to the wrong turn.
    const messages = [turn("assistant", "hi"), turn("user", "second in the window")];

    expect(outlineOf(messages)).toEqual([{ index: 1, label: "second in the window" }]);
  });
});

describe("AgentTranscriptOutline", () => {
  test("clicking an entry scrolls its turn into view", () => {
    const messages = [turn("user", "first"), turn("assistant", "…"), turn("user", "second")];
    const scrollIntoView = vi.fn();
    vi.spyOn(document, "getElementById").mockReturnValue({
      scrollIntoView,
    } as unknown as HTMLElement);

    render(<AgentTranscriptOutline messages={messages} />);
    fireEvent.click(within(screen.getByTestId("transcript-outline")).getByText("second"));

    expect(document.getElementById).toHaveBeenCalledWith(turnDomId(2));
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start", behavior: "smooth" });
    vi.restoreAllMocks();
  });

  test("a window with no prompts says so rather than rendering an empty list", () => {
    render(<AgentTranscriptOutline messages={[turn("assistant", "…")]} />);

    expect(screen.getByText(/no prompts/i)).toBeInTheDocument();
    expect(screen.queryByTestId("transcript-outline")).toBeNull();
  });
});
