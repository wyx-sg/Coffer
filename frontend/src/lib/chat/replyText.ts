// src/lib/chat/replyText.ts — the text a "Copy reply" puts on the clipboard:
// the reply's text blocks, in order, one blank line apart (tool calls and
// results are not part of what the agent said).
import type { ContentBlock } from "@/lib/api/chat";

export function replyText(blocks: readonly ContentBlock[]): string {
  return blocks
    .filter((b) => b.type === "text" && b.text)
    .map((b) => b.text)
    .join("\n\n");
}
