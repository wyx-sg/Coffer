// frontend/src/components/knowledge/navRow.ts
// The Knowledge tree's rows, shared by every node so the tree reads as one
// (Foundations 0.6.04, boards 5.1.01, 5.1.09): 28px rows, a 12px chevron slot
// and a 15px icon, a 16px indent a level from an 8px gutter, folders and
// collections (and the two named nodes, Recent changes and Inbox) in the sans
// face at 13, files in the mono face at 12, the open row filled
// `surface-selected` with no accent text. A count is 11 text-subtle.
export const NAV_ROW =
  "flex h-7 w-full min-w-0 items-center gap-1.5 rounded-item pr-2 text-left text-text transition-colors";
export const NAV_ROW_IDLE = "hover:bg-surface-hover";
export const NAV_ROW_ACTIVE = "bg-surface-selected";
/** A document's file name. */
export const NAV_NAME = "min-w-0 flex-1 truncate font-mono text-xs";
/** A folder or a collection name: sans, 13. */
export const NAV_FOLDER = "min-w-0 flex-1 truncate text-sm";
/** A named node: Recent changes, Inbox. */
export const NAV_LABEL = "min-w-0 flex-1 truncate text-sm";
/** The chevron's slot, kept blank on a row that has none so icons line up. */
export const NAV_CHEVRON = "inline-flex w-3 shrink-0 items-center justify-center text-text-subtle";
export const NAV_ICON = "size-[15px] shrink-0 text-text-subtle";
/** A count beside a node (only the Inbox's pending count): 11 text-subtle. */
export const NAV_COUNT = "shrink-0 text-2xs tabular-nums text-text-subtle";

/** The inline indent of a row at `depth` (0 = a collection). */
export function navIndent(depth: number): { paddingLeft: number } {
  return { paddingLeft: 8 + depth * 16 };
}
