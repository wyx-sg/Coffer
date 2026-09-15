// frontend/src/lib/hooks/useBeforeUnload.ts — ask the browser to confirm
// leaving the page while `enabled` (an unsaved draft is on screen). The
// listener is only attached while needed, so an idle page keeps the default
// instant reload/close.
import { useEffect } from "react";

export function useBeforeUnload(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Legacy browsers key the prompt off a non-empty returnValue.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [enabled]);
}
