// src/lib/conversations/lastWorkingDir.ts
// The working directory the last New conversation started in, remembered in
// this browser so the next one's dialog opens on it. A per-viewer convenience:
// storage that is blocked or empty simply leaves the field blank (the turn then
// runs in Coffer's own workspace).
const KEY = "coffer.conversations.lastWorkingDir";

export function readLastWorkingDir(): string | null {
  try {
    return localStorage.getItem(KEY) || null;
  } catch {
    return null;
  }
}

export function rememberWorkingDir(dir: string | null): void {
  try {
    if (dir) localStorage.setItem(KEY, dir);
  } catch {
    // Blocked storage: nothing to remember, and nothing breaks.
  }
}
