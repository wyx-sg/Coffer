// components/chat/Composer.tsx
// Text input + send button pinned at the bottom of the message thread. While a
// turn streams the Send button becomes a Stop button in the same slot; the
// input itself stays live, since a message sent mid-turn queues server-side.
// Files attach through the paperclip, by dropping them on the composer, or by
// pasting an image; each uploads at once and shows as a chip, and Send waits
// until every upload is done (spec chat "Attach files from the Chat page composer").
import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { Paperclip, Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ChatAttachment } from "@/lib/api/chat";
import { useComposerAttachments } from "@/lib/hooks/useComposerAttachments";
import { useFileDrop } from "@/lib/hooks/useFileDrop";
import { cn, formatBytes } from "@/lib/utils";
import { AttachmentChip } from "./AttachmentChip";

interface Props {
  /**
   * Send the message with the uploads that finished, in attach order. May
   * return a promise of whether the send was accepted: the chips stay attached
   * until it resolves `true`, so a refused send (the error surfaces wherever the
   * caller shows send errors) can be retried with the same files. Returning
   * nothing counts as accepted.
   */
  onSend: (text: string, attachments: ChatAttachment[]) => void | Promise<boolean>;
  /**
   * Hard-disable the composer (textarea + send). Used for the brief
   * draft-creation window — NOT for streaming, which never locks the composer.
   */
  disabled?: boolean;
  /**
   * True while a turn streams. The composer stays ENABLED — a message sent now
   * queues server-side. Swaps Send for Stop and shows a "will queue" hint.
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
  // A send whose outcome is still pending: its chips are not sent twice.
  const [sending, setSending] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const files = useComposerAttachments();
  const { dragging, handlers: dropHandlers } = useFileDrop(disabled, files.add);

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

  // A message needs words or a finished file, and never leaves while an upload
  // is in flight or a failed one is still attached — nothing is dropped silently.
  const hasContent = value.trim().length > 0 || files.ready.length > 0;
  const canSend = hasContent && !files.uploading && !files.failed && !disabled && !sending;

  const handleSend = () => {
    if (!canSend) return;
    const sentKeys = files.readyKeys;
    const result = onSend(value.trim(), files.ready);
    setValue("");
    textareaRef.current?.focus();
    if (!result) {
      files.clear(sentKeys);
      return;
    }
    // Keep the chips until the send is accepted; only the ones sent are cleared,
    // so a file attached meanwhile stays.
    setSending(true);
    void result
      .then((accepted) => {
        if (accepted) files.clear(sentKeys);
      })
      .finally(() => setSending(false));
  };

  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const images = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith("image/"));
    if (images.length === 0) return;
    files.add(images);
    // Keep any text that came with the image (a copied table, a caption).
    if (!e.clipboardData.getData("text/plain")) e.preventDefault();
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

  const showStop = streaming && !!onStop;

  return (
    <div
      className={cn(
        "border-t border-border bg-background px-4 py-3",
        dragging && "bg-accent ring-2 ring-inset ring-ring",
      )}
      {...dropHandlers}
      data-testid="composer"
    >
      {files.items.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-1.5" aria-label={t("chat.attachments.listLabel")}>
          {files.items.map((it) => (
            <li key={it.key}>
              <AttachmentChip
                name={it.name}
                detail={formatBytes(it.size)}
                mime={it.mime}
                state={it.status === "ready" ? undefined : it.status}
                error={it.error}
                onRemove={() => files.remove(it.key)}
              />
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          data-testid="composer-file-input"
          onChange={(e) => {
            files.add(Array.from(e.target.files ?? []));
            // Reset so picking the same file again still fires a change.
            e.target.value = "";
          }}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          aria-label={t("chat.composer.attach")}
          className="mb-0.5 shrink-0"
        >
          <Paperclip className="size-4" aria-hidden="true" />
        </Button>
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={dragging ? t("chat.composer.dropHint") : t("chat.composer.placeholder")}
          disabled={disabled}
          rows={1}
          className="max-h-[200px] min-h-[40px] resize-none py-2 leading-5"
          aria-label={t("chat.composer.ariaLabel")}
        />
        {showStop ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onStop}
            aria-label={t("chat.composer.stop")}
            className="mb-0.5 shrink-0"
          >
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            onClick={handleSend}
            disabled={!canSend}
            aria-label={t("chat.composer.send")}
            className="mb-0.5 shrink-0"
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>
      {streaming && (
        <p className="mt-1.5 text-xs text-muted-foreground">{t("chat.composer.streaming")}</p>
      )}
    </div>
  );
});

Composer.displayName = "Composer";
