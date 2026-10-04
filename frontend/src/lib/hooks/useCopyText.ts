// src/lib/hooks/useCopyText.ts — copy a string to the clipboard and say so for a moment.
import { useCallback, useEffect, useRef, useState } from "react";

const COPIED_MS = 1500;

/** `copy(text)` writes it to the clipboard; `copied` is true briefly after. */
export function useCopyText(): { copied: boolean; copy: (text: string) => void } {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );
  const copy = useCallback((text: string) => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), COPIED_MS);
    });
  }, []);
  return { copied, copy };
}
