// frontend/src/lib/fsActions.ts — one way to take a managed file (or its folder)
// to the OS: open it in the user's editor, or reveal it in the file manager.
//
// Coffer's file viewers are read-only; editing happens in the user's own tools.
// On the packaged desktop app (Tauri) this goes through tauri-plugin-opener; on
// the web it goes through the loopback daemon (spec 004 FR-039, ADR-033), which
// is always on the user's own machine. The desktop path falls back to the daemon
// if the native plugin is unavailable. Either way the surface behaves the same —
// there is no copy-path fallback anymore.
import { fsApi } from "@/lib/api/fs";
import { isTauri } from "@/lib/tauri";

// Static import specifier so Vite bundles/code-splits the plugin for the packaged
// WebView; isTauri() guards invocation on the web. Mirrors FolderPicker.
async function tauriOpen(path: string, withApp: string): Promise<void> {
  const { openPath } = await import("@tauri-apps/plugin-opener");
  await openPath(path, withApp || undefined);
}

async function tauriReveal(path: string): Promise<void> {
  const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
  await revealItemInDir(path);
}

/** Open/reveal actions wired to Tauri on desktop, the daemon on web. */
export function useFsActions(): {
  open: (path: string, withApp: string) => Promise<void>;
  reveal: (path: string) => Promise<void>;
} {
  const open = async (path: string, withApp: string): Promise<void> => {
    if (isTauri()) {
      try {
        await tauriOpen(path, withApp);
        return;
      } catch {
        // Native plugin unavailable — fall back to the daemon.
      }
    }
    await fsApi.open(path, withApp || undefined);
  };

  const reveal = async (path: string): Promise<void> => {
    if (isTauri()) {
      try {
        await tauriReveal(path);
        return;
      } catch {
        // Native plugin unavailable — fall back to the daemon.
      }
    }
    await fsApi.reveal(path);
  };

  return { open, reveal };
}
