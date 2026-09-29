// frontend/src/components/knowledge/navRow.ts
// The Knowledge tree's row classes, shared by every node so the tree reads as
// one — the same rows the skill Files tab draws.
export const NAV_ROW =
  "flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors";
export const NAV_ROW_IDLE = "text-text-muted hover:bg-surface-hover hover:text-text";
export const NAV_ROW_ACTIVE = "bg-surface-selected text-text";
