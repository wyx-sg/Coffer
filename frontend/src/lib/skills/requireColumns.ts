// src/lib/skills/requireColumns.ts — the grid of one Requires-tab group; its rows (SkillRequireRow) are subgrids of it.
import { cn } from "@/lib/utils";

/** The columns of a group's list; its rows are subgrids of them. */
export function requireColumns(withKind: boolean): string {
  return cn(
    "grid gap-x-3",
    withKind
      ? "grid-cols-[minmax(124px,max-content)_88px_minmax(0,1fr)_170px_128px]"
      : "grid-cols-[minmax(124px,max-content)_minmax(0,1fr)_170px_128px]",
  );
}
