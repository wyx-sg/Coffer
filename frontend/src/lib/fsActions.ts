// frontend/src/lib/fsActions.ts — one way to take a managed file (or its folder)
// to the OS: open it in the user's editor, or reveal it in the file manager.
//
// Coffer's file viewers are read-only; editing happens in the user's own tools.
// The browser can't reach the filesystem, so both actions go through the
// loopback daemon (spec 004 FR-039, ADR-033), which is always on the user's own
// machine. There is no copy-path fallback.
import { fsApi } from "@/lib/api/fs";

/** Open/reveal actions, wired to the loopback daemon. */
export function useFsActions(): {
  open: (path: string, withApp: string) => Promise<void>;
  reveal: (path: string) => Promise<void>;
} {
  const open = async (path: string, withApp: string): Promise<void> => {
    await fsApi.open(path, withApp || undefined);
  };

  const reveal = async (path: string): Promise<void> => {
    await fsApi.reveal(path);
  };

  return { open, reveal };
}
