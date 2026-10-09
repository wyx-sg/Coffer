// frontend/src/components/channel/useSettingDraft.ts
// A typed field on an auto-saving settings page: it holds what was typed, and
// commits the parsed value when the person finishes the field — on blur or
// Enter, like the retention days on Settings → Data — and only when it parses
// and differs from what was last saved. A value half typed ("3" on the way to
// "32") is never saved, so it never takes effect. An invalid entry stays on
// screen (the field shows its own error) and is never saved. A pending value
// is also committed on unmount, so leaving the tab never drops the last edit.
//
// Spread `commitProps` on the field, or on an element wrapping it: blur and
// keydown both bubble in React.
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

export function useSettingDraft<T>(
  initial: string,
  parse: (text: string) => T | null,
  commit: (value: T) => void,
) {
  const [text, setText] = useState(initial);
  const queued = useRef<{ value: T } | null>(null);
  const saved = useRef(JSON.stringify(parse(initial)));
  const commitRef = useRef(commit);
  commitRef.current = commit;

  const flush = useCallback(() => {
    const next = queued.current;
    queued.current = null;
    if (!next) return;
    const key = JSON.stringify(next.value);
    if (key === saved.current) return;
    saved.current = key;
    commitRef.current(next.value);
  }, []);

  const change = useCallback(
    (next: string) => {
      setText(next);
      const value = parse(next);
      queued.current = value === null ? null : { value };
    },
    [parse],
  );

  const onKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Enter") flush();
    },
    [flush],
  );

  useEffect(() => flush, [flush]);

  return { text, change, flush, commitProps: { onBlur: flush, onKeyDown } };
}
