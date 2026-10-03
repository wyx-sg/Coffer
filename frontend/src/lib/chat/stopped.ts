// src/lib/chat/stopped.ts — what the "Stopped by you." line adds when a tool
// call was still running at the stop: a file-writing tool left its edit
// unfinished, a shell tool its command. Any other tool (or none) adds nothing,
// since the page cannot say what was left undone. Pure and unit-tested alone.
import type { ContentBlock } from "@/lib/api/chat";

export type UnfinishedWork = "edit" | "command";

const FILE_WRITING = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit", "file_change"]);
const SHELL = new Set(["Bash", "shell"]);

/** The kind of work the last still-running tool call (one with no result) left undone, if known. */
export function unfinishedWork(blocks: readonly ContentBlock[]): UnfinishedWork | null {
  const answered = new Set(
    blocks.filter((b) => b.type === "tool_result").map((b) => b.tool_use_id),
  );
  const running = blocks.filter(
    (b) => b.type === "tool_use" && !(b.tool_use_id && answered.has(b.tool_use_id)),
  );
  const last = running.at(-1);
  if (!last?.tool_name) return null;
  if (FILE_WRITING.has(last.tool_name)) return "edit";
  if (SHELL.has(last.tool_name)) return "command";
  return null;
}
