// frontend/src/components/knowledge/navRow.ts
// The Knowledge tree's rows, shared by every node so the tree reads as one
// (boards 5.1.01, 5.1.09): 28px rows, a 12px chevron slot and a 14px icon, a
// 14px indent a level from an 8px gutter, collection / folder / file names in
// the mono face and the two named nodes (Recent changes, Inbox) in the text
// face, the open row filled `surface-selected`.
export const NAV_ROW =
  "flex h-7 w-full min-w-0 items-center gap-1.5 rounded-item pr-2 text-left text-text transition-colors";
export const NAV_ROW_IDLE = "hover:bg-surface-hover";
export const NAV_ROW_ACTIVE = "bg-surface-selected";
/** A file-system name: a collection, a folder, a document. */
export const NAV_NAME = "min-w-0 flex-1 truncate font-mono text-xs";
/** A named node: Recent changes, Inbox. */
export const NAV_LABEL = "min-w-0 flex-1 truncate text-sm";
/** The chevron's slot, kept blank on a row that has none so icons line up. */
export const NAV_CHEVRON = "inline-flex w-3 shrink-0 items-center justify-center text-text-subtle";
export const NAV_ICON = "size-3.5 shrink-0 text-text-subtle";
/** A count pill beside a named node; the Inbox's is toned warning. */
export const NAV_PILL =
  "inline-flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-full px-[5px] text-2xs font-bold tabular-nums";

/** The inline indent of a row at `depth` (0 = a collection). */
export function navIndent(depth: number): { paddingLeft: number } {
  return { paddingLeft: 8 + depth * 14 };
}
