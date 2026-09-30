// src/lib/conversations/filesChanged.ts
// "Files changed" under an agent's reply on the Conversations page: the files
// its tool calls wrote, with the lines each added and removed, read from the
// calls themselves — Claude Code's Edit / MultiEdit / Write / NotebookEdit and
// Codex's file_change (whose changes carry a unified diff). A call that failed
// changed nothing and is left out. Pure, so the counting is unit-tested alone.
import type { ContentBlock } from "@/lib/api/chat";

export interface FileChange {
  path: string;
  added: number;
  removed: number;
}

function lineCount(text: unknown): number {
  if (typeof text !== "string" || text === "") return 0;
  return text.replace(/\n$/, "").split("\n").length;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

/** Lines a unified diff adds and removes (its `+++` / `---` headers excluded). */
function diffCounts(diff: unknown): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  if (typeof diff !== "string") return { added, removed };
  for (const line of diff.split("\n")) {
    if (line.startsWith("+++") || line.startsWith("---")) continue;
    if (line.startsWith("+")) added += 1;
    else if (line.startsWith("-")) removed += 1;
  }
  return { added, removed };
}

/** What one tool call changed, as zero or more files. */
function changesOf(use: ContentBlock): FileChange[] {
  const input = (use.tool_input ?? {}) as Record<string, unknown>;
  switch (use.tool_name) {
    case "Edit": {
      const path = str(input.file_path);
      if (!path) return [];
      return [{ path, added: lineCount(input.new_string), removed: lineCount(input.old_string) }];
    }
    case "MultiEdit": {
      const path = str(input.file_path);
      if (!path) return [];
      const edits = Array.isArray(input.edits) ? (input.edits as Record<string, unknown>[]) : [];
      return [
        {
          path,
          added: edits.reduce((n, e) => n + lineCount(e.new_string), 0),
          removed: edits.reduce((n, e) => n + lineCount(e.old_string), 0),
        },
      ];
    }
    case "Write": {
      const path = str(input.file_path);
      return path ? [{ path, added: lineCount(input.content), removed: 0 }] : [];
    }
    case "NotebookEdit": {
      const path = str(input.notebook_path);
      return path ? [{ path, added: lineCount(input.new_source), removed: 0 }] : [];
    }
    case "file_change": {
      const changes = Array.isArray(input.changes)
        ? (input.changes as Record<string, unknown>[])
        : [];
      return changes.flatMap((c) => {
        const path = str(c.path);
        return path ? [{ path, ...diffCounts(c.diff) }] : [];
      });
    }
    default:
      return [];
  }
}

/** The files a reply's tool calls changed, first write first, one row per file. */
export function filesChanged(blocks: readonly ContentBlock[]): FileChange[] {
  const failed = new Set(
    blocks
      .filter((b) => b.type === "tool_result" && b.error)
      .map((b) => b.tool_use_id)
      .filter((id): id is string => !!id),
  );
  const byPath = new Map<string, FileChange>();
  for (const block of blocks) {
    if (block.type !== "tool_use") continue;
    if (block.tool_use_id && failed.has(block.tool_use_id)) continue;
    for (const change of changesOf(block)) {
      const seen = byPath.get(change.path);
      if (seen) {
        seen.added += change.added;
        seen.removed += change.removed;
      } else {
        byPath.set(change.path, { ...change });
      }
    }
  }
  return [...byPath.values()];
}
