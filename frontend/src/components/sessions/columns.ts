// src/components/sessions/columns.ts — the column layouts of a session row (SessionRow).

// The columns: title, channel, agent, directory, time, actions.
export const GRID = {
  channel_agent: "grid-cols-[minmax(0,1fr)_200px_120px_160px_52px_300px]",
  channel: "grid-cols-[minmax(0,1fr)_200px_160px_52px_300px]",
  agent: "grid-cols-[minmax(0,1fr)_120px_160px_52px_300px]",
  plain: "grid-cols-[minmax(0,1fr)_160px_52px_300px]",
} as const;

/** The min-width a list of these rows needs before it scrolls sideways. */
export const ROW_MIN_WIDTH = {
  channel_agent: "min-w-[65rem]",
  channel: "min-w-[55rem]",
  agent: "min-w-[53rem]",
  plain: "min-w-[45rem]",
} as const;

/** Which of the optional columns a list shows. */
export function columnsOf(showChannel: boolean, showAgent: boolean): SessionColumns {
  if (showChannel && showAgent) return "channel_agent";
  if (showChannel) return "channel";
  return showAgent ? "agent" : "plain";
}

/** Which of the optional columns a row lays out. */
export type SessionColumns = keyof typeof GRID;
