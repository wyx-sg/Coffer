// lib/chatCwd.ts
// Remembers the working directories used for CLI-agent chats, so the new-chat
// draft can default to the last one and offer recents — instead of forcing the
// user to type an absolute path every time (the Claude Code / Codex apps do the
// same). Persisted in localStorage; most-recent-first, de-duplicated, capped.
const STORAGE_KEY = "coffer.chat.recentCwds";
const MAX_RECENTS = 8;

function read(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((p): p is string => typeof p === "string") : [];
  } catch {
    return [];
  }
}

/** Recent working directories, most-recent first. */
export function getRecentCwds(): string[] {
  return read();
}

/** The last-used working directory, or null if there is none. */
export function lastCwd(): string | null {
  return read()[0] ?? null;
}

/** Record a working directory as the most-recently-used (no-op for blanks). */
export function pushRecentCwd(path: string): void {
  const trimmed = path.trim();
  if (!trimmed) return;
  const next = [trimmed, ...read().filter((p) => p !== trimmed)].slice(0, MAX_RECENTS);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable (private mode / quota) — recents are a convenience,
    // never a correctness requirement, so silently skip.
  }
}
