// frontend/src/components/files/middlePath.ts
// A path shortened in its MIDDLE (Foundations 0.6.03): the start, so you know
// whose it is, and the end, so you know which file —
// `~/.claude/projects/…/memory/feedback-worktree-development.md`. Whole
// segments only; a path that fits is returned as it is.

/** Shorten `path` to roughly `max` characters by dropping middle segments. */
export function middlePath(path: string, max = 64): string {
  if (path.length <= max) return path;
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  let head = parts.slice(0, 2).join("/");
  let tail = parts.slice(-2).join("/");
  // Grow the tail while there is room, then the head.
  let i = parts.length - 3;
  while (i > 2 && head.length + 3 + parts[i].length + 1 + tail.length <= max) {
    tail = `${parts[i]}/${tail}`;
    i -= 1;
  }
  if (head.length + 3 + tail.length > max && parts.length > 3) head = parts[0];
  return `${head}/…/${tail}`;
}

/** A Markdown file by its name. */
export function isMarkdownPath(path: string): boolean {
  return /\.mdx?$/i.test(path);
}
