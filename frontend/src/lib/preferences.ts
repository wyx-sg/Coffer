// frontend/src/lib/preferences.ts
//
// Small client-side UI preferences persisted in localStorage (same pattern as
// the sidebar-collapsed flag and the language choice). These are pure display
// settings — no user data — so they live in the browser, not the daemon.
import { useCallback, useSyncExternalStore } from "react";

// Storage can be blocked (private windows, cleared or denied site data): every
// read falls back to the default and every write is skipped, because these are
// per-viewer conveniences and `getSnapshot` runs in render.
function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Not persisted; the choice lasts until the page reloads.
  }
}

// Tiny pub/sub so a change in Settings updates any mounted reader live (the
// browser only fires the native `storage` event across tabs, not same-tab).
const listeners = new Set<() => void>();
function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

const PREFERRED_EDITOR_KEY = "coffer.preferredEditor";

/**
 * The user's preferred external editor for opening managed files. The stored
 * value is an application name / path or a launch command (e.g. "code",
 * "cursor", or a full ".app" path). An empty string means "use the operating
 * system's default application". Like the other preferences here it lives in
 * the browser, never the daemon.
 */
export function getPreferredEditor(): string {
  return readStored(PREFERRED_EDITOR_KEY) ?? "";
}

function setPreferredEditor(editor: string): void {
  const trimmed = editor.trim();
  if (trimmed) {
    writeStored(PREFERRED_EDITOR_KEY, trimmed);
  } else {
    // Empty / whitespace clears the override → fall back to the OS default.
    writeStored(PREFERRED_EDITOR_KEY, null);
  }
  listeners.forEach((cb) => cb());
}

/** Reactive read of the preferred external editor ("" = OS default). */
export function usePreferredEditor(): string {
  return useSyncExternalStore(subscribe, getPreferredEditor, () => "");
}

/** Setter hook for the Settings control. */
export function useSetPreferredEditor(): (editor: string) => void {
  return useCallback((editor: string) => setPreferredEditor(editor), []);
}

const PREFERRED_TERMINAL_KEY = "coffer.preferredTerminal";

/**
 * The terminal Coffer opens an agent session in: a launcher value from the
 * daemon's detected list (`GET /fs/terminals`) or a custom command template
 * holding `{cwd}` and `{command}`. An empty string means the system terminal.
 * Browser-only like the editor; it travels to the daemon only as the `terminal`
 * of an open, read at click time.
 */
export function getPreferredTerminal(): string {
  return readStored(PREFERRED_TERMINAL_KEY) ?? "";
}

function setPreferredTerminal(terminal: string): void {
  const trimmed = terminal.trim();
  writeStored(PREFERRED_TERMINAL_KEY, trimmed || null);
  listeners.forEach((cb) => cb());
}

/** Reactive read of the preferred terminal ("" = the system terminal). */
export function usePreferredTerminal(): string {
  return useSyncExternalStore(subscribe, getPreferredTerminal, () => "");
}

/** Setter hook for the Settings control. */
export function useSetPreferredTerminal(): (terminal: string) => void {
  return useCallback((terminal: string) => setPreferredTerminal(terminal), []);
}

/** The agents a hand-off can start. */
export type HandoffAgent = "claude_code" | "codex";

const HANDOFF_AGENT_KEY = "coffer.handoffAgent";

/** The stored hand-off agent, or "" when none is stored (or the stored value is not one we know). */
export function getHandoffAgent(): HandoffAgent | "" {
  const raw = readStored(HANDOFF_AGENT_KEY);
  return raw === "claude_code" || raw === "codex" ? raw : "";
}

function setHandoffAgent(agent: HandoffAgent | ""): void {
  writeStored(HANDOFF_AGENT_KEY, agent || null);
  listeners.forEach((cb) => cb());
}

/** Reactive read of the stored hand-off agent ("" = none chosen). */
export function useHandoffAgentPreference(): HandoffAgent | "" {
  return useSyncExternalStore(subscribe, getHandoffAgent, () => "");
}

/** Setter hook for the Settings control. */
export function useSetHandoffAgent(): (agent: HandoffAgent | "") => void {
  return useCallback((agent: HandoffAgent | "") => setHandoffAgent(agent), []);
}
