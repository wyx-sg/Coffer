// frontend/src/components/chat/ChatComposer.tsx
//
// The message input + Send / Stop control at the bottom of a conversation.
// Enter sends; Shift+Enter inserts a newline. While a turn streams the Send
// button becomes a Stop button wired to the /stop endpoint.
import { useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Send, Square } from "lucide-react";

import { Button } from "@/components/ui/button";

export function ChatComposer({
  streaming,
  disabled,
  onSend,
  onStop,
}: {
  streaming: boolean;
  /** Archived conversations are read-only — the composer is disabled. */
  disabled?: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || streaming || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-border bg-background p-4">
      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          rows={1}
          placeholder={disabled ? t("chat.composerDisabled") : t("chat.composerPlaceholder")}
          aria-label={t("chat.composerPlaceholder")}
          className="max-h-40 min-h-10 flex-1 resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        />
        {streaming ? (
          <Button type="button" variant="destructive" onClick={onStop} aria-label={t("chat.stop")}>
            <Square className="size-4" /> {t("chat.stop")}
          </Button>
        ) : (
          <Button
            type="button"
            onClick={submit}
            disabled={disabled || text.trim().length === 0}
            aria-label={t("chat.send")}
          >
            <Send className="size-4" /> {t("chat.send")}
          </Button>
        )}
      </div>
    </div>
  );
}
