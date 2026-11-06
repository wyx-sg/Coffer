// src/lib/secretClipboard.ts — copying a revealed secret (ADR a-copied-secret-is-marked-concealed-and-cleared-after-90-seconds).
import { inDesktopShell, shellInvoke } from "@/lib/tauri";

/**
 * Copy a revealed secret: through the shell, onto the pasteboard marked
 * concealed and transient so clipboard managers skip it, and cleared after
 * 90 seconds unless something else was copied since. Outside the shell (or
 * where the shell cannot) the page's own clipboard write is the fallback.
 */
export async function copySecretValue(value: string): Promise<void> {
  if (inDesktopShell()) {
    try {
      await shellInvoke<void>("copy_secret", { value });
      return;
    } catch {
      // Not a Mac: fall through to the page's clipboard.
    }
  }
  await navigator.clipboard.writeText(value);
}
