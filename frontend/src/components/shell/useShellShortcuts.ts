// src/components/shell/useShellShortcuts.ts — the shell's global keys: ⌘K / Ctrl+K for the palette, ⌘, / Ctrl+, for Settings, ⌘B / Ctrl+B for the sidebar (desktop shell).
//
// Settings' shortcut is ignored while the user types in a text field (spec
// web-ui "Open Settings as a modal from the sidebar footer"); the palette's
// works from anywhere, as editors' quick-open does.
import { useEffect, useRef } from "react";

import { isModShortcut, isTypingTarget } from "@/lib/shortcuts";

interface Handlers {
  togglePalette: () => void;
  openSettings: () => void;
  /** Given only where the sidebar has a toggle (desktop shell, md+). */
  toggleSidebar?: () => void;
}

export function useShellShortcuts(handlers: Handlers): void {
  // The latest handlers, so the listener is installed once.
  const latest = useRef(handlers);
  latest.current = handlers;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isModShortcut(event, "k")) {
        event.preventDefault();
        latest.current.togglePalette();
      } else if (isModShortcut(event, "b") && latest.current.toggleSidebar) {
        if (isTypingTarget(event.target)) return; // bold, in an editor
        event.preventDefault();
        latest.current.toggleSidebar();
      } else if (isModShortcut(event, ",") && !isTypingTarget(event.target)) {
        event.preventDefault();
        latest.current.openSettings();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
