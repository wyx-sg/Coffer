// components/chat/Composer.tsx
// The reply box pinned at the bottom of the message thread: attached files'
// chips, the text, then a toolbar with the paperclip on the left and Send on
// the right. While a turn streams Send becomes Stop in the same slot; the input
// itself stays live, since a message sent mid-turn queues server-side. Files
// attach through the paperclip, by dropping them on the composer, or by pasting
// an image; each uploads at once and shows as a chip, and Send waits until every
// upload is done (spec chat "Attach files from the Conversations page composer"). A file
// refused before upload is not a chip: one line under the box says why.
import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { Textarea } from "@/components/ui/textarea";
import type { ChatAttachment } from "@/lib/api/chat";
import { useComposerAttachments } from "@/lib/hooks/useComposerAttachments";
import { type ComposerRestore, useComposerRestore } from "@/lib/hooks/useComposerRestore";
import { useFileDrop } from "@/lib/hooks/useFileDrop";
import { cn, formatBytes } from "@/lib/utils";
import { AttachmentChip } from "./AttachmentChip";
import { ComposerToolbar } from "./ComposerToolbar";

interface Props {
  /** Send with the finished uploads, in attach order. A promise of whether it was
   *  accepted keeps the chips (and gives the text back) until it resolves true. */
  onSend: (text: string, attachments: ChatAttachment[]) => void | Promise<boolean>;
  /** Hard-disable (the draft's create window) — never for streaming. */
  disabled?: boolean;
  /** A turn is running: still enabled (a send queues), Send becomes Stop. */
  streaming?: boolean;
  onStop?: () => void;
  /** A refused message to put back once; `onRestored` then fires. */
  restore?: ComposerRestore | null;
  onRestored?: () => void;
  /** The input's placeholder — "Message Claude Code…", "Reply…", "…it queues". */
  placeholder?: string;
  /** Compact controls (agent, model, effort) shown in the footer, left of Send. */
  controls?: ReactNode;
}

/** Lets the parent load text in — a queued message pulled back to be edited. */
export interface ComposerHandle {
  setText: (text: string) => void;
}

/** Grow-then-scroll cap (px), in sync with the `max-h-[200px]` class below. */
const MAX_HEIGHT = 200;

export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  {
    onSend,
    disabled = false,
    streaming = false,
    onStop,
    restore,
    onRestored,
    placeholder,
    controls,
  },
  ref,
) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  // A send whose outcome is still pending: its chips are not sent twice.
  const [sending, setSending] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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

  useComposerRestore(restore, onRestored, setValue, files.restore);

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
    const text = value.trim();
    const result = onSend(text, files.ready);
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
        else setValue((current) => current || text); // unless something was typed since
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
    // A file dragged over the page restyles only this box — an accent border
    // and "Drop to attach" — never a full-pane overlay; the limits are said
    // only by the line under the box when a file is refused.
    <div className="px-8 pb-4 pt-2" {...dropHandlers} data-testid="composer">
      <div className="mx-auto flex w-full max-w-[960px] flex-col gap-1.5">
        <div
          className={cn(
            "flex flex-col gap-2.5 rounded-xl border bg-surface-raised pb-2.5 pl-3.5 pr-3 pt-3 transition-colors duration-fast",
            dragging ? "border-accent" : "border-border",
          )}
          data-dragging={dragging || undefined}
        >
          {files.items.length > 0 && (
            <ul
              className="flex flex-wrap gap-1.5"
              aria-label={t("conversations.attachments.listLabel")}
            >
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
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={
              dragging
                ? t("conversations.composer.dropHint")
                : (placeholder ??
                  t(
                    streaming
                      ? "conversations.composer.queuePlaceholder"
                      : "conversations.composer.placeholderAny",
                  ))
            }
            disabled={disabled}
            rows={1}
            className="max-h-[200px] min-h-6 resize-none rounded-none border-0 bg-transparent p-0 leading-6 shadow-none focus-visible:ring-0"
            aria-label={t("conversations.composer.ariaLabel")}
          />
          <ComposerToolbar
            onPickFiles={(picked) => files.add(picked)}
            disabled={disabled}
            controls={controls}
            showStop={showStop}
            onStop={onStop}
            canSend={canSend}
            onSend={handleSend}
          />
        </div>
        {files.refusal ? (
          <p role="alert" data-testid="composer-refusal" className="px-1 text-xs text-danger">
            {files.refusal}
          </p>
        ) : null}
      </div>
    </div>
  );
});

Composer.displayName = "Composer";
