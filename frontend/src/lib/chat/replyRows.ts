// src/lib/chat/replyRows.ts — an agent reply's blocks as the rows it renders:
// text and tool-call segments in the order the turn emitted them, with each run
// of three or more consecutive tool calls folded into one group row. Pure.
import type { ContentBlock } from "@/lib/api/chat";

/** One tool call of a reply: its use block and, when it has arrived, its result. */
export interface ToolCall {
  key: string;
  use: ContentBlock;
  result?: ContentBlock;
}

type Segment =
  | { kind: "text"; key: string; text: string }
  | { kind: "tool"; key: string; use: ContentBlock; result?: ContentBlock };

/**
 * An assistant turn's blocks as render segments, in the order the turn emitted
 * them: each text block is its own segment (never glued to the next one), and
 * each tool call is a card at its call's position carrying its result, wherever
 * in the turn that result arrived. A result is drawn only inside its call's card.
 */
function buildSegments(blocks: ContentBlock[]): Segment[] {
  const results = blocks.filter((b) => b.type === "tool_result");
  const segments: Segment[] = [];
  blocks.forEach((b, i) => {
    if (b.type === "text" && b.text) {
      segments.push({ kind: "text", key: `text-${i}`, text: b.text });
    } else if (b.type === "tool_use") {
      segments.push({
        kind: "tool",
        key: b.tool_use_id ?? `tool-${i}`,
        use: b,
        result: results.find((r) => r.tool_use_id === b.tool_use_id),
      });
    }
  });
  return segments;
}

/** Runs of this many consecutive tool calls fold into one group row. */
const GROUP_MIN = 3;

export type Row =
  | { kind: "text"; key: string; text: string }
  | { kind: "tool"; key: string; call: ToolCall }
  | { kind: "group"; key: string; calls: ToolCall[] };

/** Fold each run of GROUP_MIN or more consecutive tool segments into one group. */
function groupSegments(segments: Segment[]): Row[] {
  const rows: Row[] = [];
  let run: ToolCall[] = [];
  const flush = () => {
    if (run.length >= GROUP_MIN)
      rows.push({ kind: "group", key: `group-${run[0].key}`, calls: run });
    else run.forEach((call) => rows.push({ kind: "tool", key: call.key, call }));
    run = [];
  };
  for (const seg of segments) {
    if (seg.kind === "tool") run.push({ key: seg.key, use: seg.use, result: seg.result });
    else {
      flush();
      rows.push(seg);
    }
  }
  flush();
  return rows;
}

/** The rows of a reply: its segments, tool-call runs folded. */
export function buildRows(blocks: ContentBlock[]): Row[] {
  return groupSegments(buildSegments(blocks));
}
