// frontend/src/components/channel/useSettingDraft.ts
// A typed field on an auto-saving settings page: it holds what was typed, and
// commits the parsed value a moment after typing stops — but only when it
// parses. An invalid entry stays on screen (the field shows its own error)
// and is never saved. A pending commit is flushed on blur and on unmount, so
// leaving the tab never drops the last edit.
import { useCallback, useEffect, useRef, useState } from "react";

const SETTING_SAVE_DELAY_MS = 600;

export function useSettingDraft<T>(
  initial: string,
  parse: (text: string) => T | null,
  commit: (value: T) => void,
  delay = SETTING_SAVE_DELAY_MS,
) {
  const [text, setText] = useState(initial);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queued = useRef<{ value: T } | null>(null);
  const commitRef = useRef(commit);
  commitRef.current = commit;

  const flush = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const next = queued.current;
    queued.current = null;
    if (next) commitRef.current(next.value);
  }, []);

  const change = useCallback(
    (next: string) => {
      setText(next);
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      const value = parse(next);
      if (value === null) {
        queued.current = null;
        return;
      }
      queued.current = { value };
      timer.current = setTimeout(flush, delay);
    },
    [parse, delay, flush],
  );

  useEffect(() => flush, [flush]);

  return { text, change, flush };
}
