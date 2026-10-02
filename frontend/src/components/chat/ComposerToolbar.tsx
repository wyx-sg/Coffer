// components/chat/ComposerToolbar.tsx — the footer row of the reply box.
//
// The paperclip on the left; on the right the compact controls the page hands
// in (agent, model, effort — `controls`), then Send, which becomes Stop in the
// same slot while a turn streams. The hidden file input lives here too: the
// paperclip opens it and what it picks goes to `onPickFiles`.
import { useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUp, Paperclip, Square } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  onPickFiles: (files: File[]) => void;
  disabled: boolean;
  controls?: ReactNode;
  showStop: boolean;
  onStop?: () => void;
  canSend: boolean;
  onSend: () => void;
}

export function ComposerToolbar({
  onPickFiles,
  disabled,
  controls,
  showStop,
  onStop,
  canSend,
  onSend,
}: Props) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="-ml-1.5 flex items-center gap-0.5">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        data-testid="composer-file-input"
        onChange={(e) => {
          onPickFiles(Array.from(e.target.files ?? []));
          // Reset so picking the same file again still fires a change.
          e.target.value = "";
        }}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled}
        aria-label={t("conversations.composer.attach")}
      >
        <Paperclip className="size-3.5" aria-hidden="true" />
      </Button>
      <span className="ml-auto" />
      {controls ? (
        <div className="mr-1.5 flex min-w-0 items-center gap-1" data-testid="composer-controls">
          {controls}
        </div>
      ) : null}
      {showStop ? (
        <Button type="button" variant="outline" size="sm" onClick={onStop}>
          <Square aria-hidden />
          {t("conversations.composer.stop")}
        </Button>
      ) : (
        <Button
          type="button"
          size="icon-md"
          onClick={onSend}
          disabled={!canSend}
          aria-label={t("conversations.composer.send")}
        >
          <ArrowUp className="size-4" aria-hidden="true" />
        </Button>
      )}
    </div>
  );
}
