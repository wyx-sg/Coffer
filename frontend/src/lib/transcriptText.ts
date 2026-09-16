// frontend/src/lib/transcriptText.ts
//
// Separating what a person typed from what their harness prepended to it.
//
// A "user turn" in a transcript is not only the user's words. Every harness
// injects blocks into the same turn — `<system-reminder>`, `<task-notification>`,
// `<command-name>`, an environment dump — and a reader looking through the
// conversation did not write any of them and is not looking for them. Left
// undivided they take over the two places a turn is summarised: the contents
// list beside the transcript indexed entry after entry as `<task-notification>`,
// and the turn itself opened with eight lines of machinery before the question.
//
// The split is LEADING blocks only, and deliberately so: a block in the middle
// of a turn sits between two things the person wrote, and cutting there would
// rearrange their words rather than uncover them. What leads a turn is what the
// harness put in front; what follows is theirs.
//
// The shape is what identifies a block, not a list of names — naming them one
// at a time never finishes (the backend's transcript parser says the same thing
// about session titles, and learnt it from `<turn_aborted>` reaching the UI as
// one). A block is a tag-shaped span with an identifier-ish name: prose that
// merely contains a `<` — a comparison, an arrow, a shell redirect — matches
// nothing here and survives whole.

/** A paired block at the very start: `<name …> … </name>`, newline included. */
const LEADING_BLOCK = /^\s*<([A-Za-z_][\w.:-]*)(?:\s[^<>]*)?>[\s\S]*?<\/\1>[ \t]*\r?\n?/;

/** A single leading tag with no partner — `<name/>`, or an unclosed opener. */
const LEADING_TAG = /^\s*<\/?[A-Za-z_][\w.:-]*(?:\s[^<>]*)?\/?>[ \t]*\r?\n?/;

export interface TurnText {
  /** The harness blocks that led the turn, verbatim — empty when there were none. */
  harness: string;
  /** What the person wrote. Empty when the turn was nothing but harness. */
  human: string;
}

/**
 * One turn split into what the harness prepended and what the person wrote.
 *
 * Both halves are returned rather than one discarded: the blocks are part of
 * the record, and a view that dropped them would be telling the reader the turn
 * said less than it did.
 */
export function splitTurnText(text: string): TurnText {
  let rest = text;
  for (;;) {
    const match = LEADING_BLOCK.exec(rest) ?? LEADING_TAG.exec(rest);
    if (!match) break;
    rest = rest.slice(match[0].length);
  }
  const harness = rest === text ? "" : text.slice(0, text.length - rest.length);
  return { harness, human: rest };
}

/**
 * The first line the person actually wrote in this turn, or `""` when they
 * wrote none — what a one-line summary of the turn should say.
 */
export function firstHumanLine(text: string): string {
  const { human } = splitTurnText(text);
  for (const line of human.split("\n")) {
    if (line.trim().length > 0) return line.trim();
  }
  return "";
}
