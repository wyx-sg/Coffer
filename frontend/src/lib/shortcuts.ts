// src/lib/shortcuts.ts — the shell's keyboard shortcuts: ⌘ on macOS, Ctrl elsewhere.
//
// ⌘K / Ctrl+K opens the command palette and ⌘, / Ctrl+, opens Settings (spec
// web-ui "Jump to any page or object from a command palette", "Open Settings as
// a modal from the sidebar footer"). Settings' shortcut is ignored while the
// user is typing in a text field, where a comma is just a comma.

function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent);
}

/** The shortcut as the user reads it: `⌘K` on macOS, `Ctrl+K` elsewhere. */
export function shortcutLabel(key: string): string {
  return isMac() ? `⌘${key.toUpperCase()}` : `Ctrl+${key.toUpperCase()}`;
}

/** Whether a key event is the platform's modifier plus `key` (and nothing else). */
export function isModShortcut(event: KeyboardEvent, key: string): boolean {
  const mod = isMac() ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  return mod && !event.altKey && !event.shiftKey && event.key.toLowerCase() === key;
}

/** Whether focus is somewhere the user types text. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag !== "INPUT") return false;
  const type = (target as HTMLInputElement).type;
  return !["checkbox", "radio", "button", "submit", "reset", "range", "color"].includes(type);
}
