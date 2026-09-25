// src/lib/hooks/useComposerRestore.ts
// Puts a refused message back into a composer that never sent it: the draft's
// first message is sent only after its conversation is created, by which time
// the draft's own composer is gone — so a refusal hands the text and chips to
// the new conversation's composer instead of losing them.
import { useEffect, type Dispatch, type SetStateAction } from "react";

import type { ChatAttachment } from "@/lib/api/chat";

export interface ComposerRestore {
  text: string;
  attachments: ChatAttachment[];
}

/** Apply `restore` once (text only into an empty input), then call `onRestored`. */
export function useComposerRestore(
  restore: ComposerRestore | null | undefined,
  onRestored: (() => void) | undefined,
  setText: Dispatch<SetStateAction<string>>,
  restoreFiles: (uploads: ChatAttachment[]) => void,
): void {
  useEffect(() => {
    if (!restore) return;
    setText((current) => current || restore.text);
    restoreFiles(restore.attachments);
    onRestored?.();
  }, [restore, onRestored, setText, restoreFiles]);
}
