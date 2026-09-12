// components/chat/Composer.tsx
// Text input + send button pinned at the bottom of the message thread.
import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  onSend: (text: string) => void;
  /**
   * Hard-disable the composer (textarea + send). Used for the brief
   * draft-creation window — NOT for streaming, which never locks the composer.
   */
  disabled?: boolean;
  /**
   * True while a turn streams. The composer stays ENABLED — a message sent now
   * queues server-side. Drives the Stop button and a subtle "will queue" hint.
   */
  streaming?: boolean;
  /** Called when the user stops an in-flight turn. Shown only while streaming. */
  onStop?: () => void;
}

/**
 * Imperative handle: lets the parent load text into the composer. Used when the
 * user edits a queued message — it is pulled out of the queue and back into the
 * input to amend, then re-sent (re-queuing it at the tail).
 */
export interface ComposerHandle {
  setText: (text: string) => void;
}

/**
 * Max height (px) the textarea grows to before it scrolls internally — roughly
 * ten lines, matching Claude Code / Codex's grow-then-scroll input. Kept in sync
 * with the `max-h-[200px]` class below.
 */
const MAX_HEIGHT = 200;

export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  { onSend, disabled = false, streaming = false, onStop },
  ref,
) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow: remeasure on every value change so the box tracks its content,
  // capped at MAX_HEIGHT where it switches to internal scrolling. Sending clears
  // `value`, which runs this again and collapses the box back to a single row.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight, MAX_HEIGHT);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? "auto" : "hidden";
  }, [value]);

  useImperativeHandle(ref, () => ({
    setText: (text: string) => {
      setValue(text);
      textareaRef.current?.focus();
    },
  }));

  const canSend = value.trim().length > 0 && !disabled;

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // While an IME composition is active, Enter commits the candidate text — it
    // must NOT also send the message. Without this guard a CJK user pressing
    // Enter to accept a pinyin candidate sends the half-composed text, then
    // sends again on the real Enter, so one message posts twice. `isComposing`
    // lives on the native event (the synthetic event does not surface it).
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="flex items-end gap-2">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("chat.composer.placeholder")}
          disabled={disabled}
          rows={1}
          className="max-h-[200px] min-h-[40px] resize-none py-2 leading-5"
          aria-label={t("chat.composer.ariaLabel")}
        />
        <Button
          size="sm"
          onClick={handleSend}
          disabled={!canSend}
          aria-label={t("chat.composer.send")}
          className="mb-0.5 shrink-0"
        >
          <Send className="size-4" />
        </Button>
      </div>
      {streaming && (
        <div className="mt-1.5 flex items-center gap-2">
          {onStop && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 gap-1 px-2 text-xs"
              onClick={onStop}
              aria-label={t("chat.composer.stop")}
            >
              <Square className="size-3" />
              {t("chat.composer.stop")}
            </Button>
          )}
          <span className="text-xs text-muted-foreground">{t("chat.composer.streaming")}</span>
        </div>
      )}
    </div>
  );
});

Composer.displayName = "Composer";
