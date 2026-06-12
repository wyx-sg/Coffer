// components/chat/Composer.tsx
// Text input + send button pinned at the bottom of the message thread.
import { useState, useRef, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  /** Called when the user stops an in-flight turn. Shown only while streaming. */
  onStop?: () => void;
}

export function Composer({ onSend, disabled = false, onStop }: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = value.trim().length > 0 && !disabled;

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
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
          className="min-h-[40px] resize-none overflow-hidden py-2 leading-5"
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
      {disabled && (
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
          <span className="text-xs text-muted-foreground">
            {t("chat.composer.streaming")}
          </span>
        </div>
      )}
    </div>
  );
}
