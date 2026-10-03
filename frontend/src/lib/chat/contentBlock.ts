import type { ContentBlock } from "@/lib/api/chat";

/**
 * A content block the page builds itself — an optimistic echo, a block
 * folded in from a live turn event — in the wire's full shape: the daemon
 * always sends every field, `null` where a block's type has none, so a block
 * built here carries the same nulls and renders exactly like a fetched one.
 */
export function contentBlock(
  fields: Partial<ContentBlock> & Pick<ContentBlock, "type">,
): ContentBlock {
  return {
    text: null,
    tool_use_id: null,
    tool_name: null,
    tool_input: null,
    output: null,
    error: null,
    filename: null,
    mime: null,
    attachment_id: null,
    size: null,
    duration_ms: null,
    question: null,
    ...fields,
  };
}
