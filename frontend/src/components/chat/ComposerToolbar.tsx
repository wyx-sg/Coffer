// components/chat/ComposerToolbar.tsx — the footer row of the reply box.
//
// The paperclip on the left, then the working folder (a read-only chip in an
// open conversation, the draft's picker before the first send); on the right the
// compact controls the page hands in (agent, model, effort — `controls`), then
// Send, which becomes Stop in the same slot while a turn streams. The hidden file input lives here too: the
// paperclip opens it and what it picks goes to `onPickFiles`.
import { useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUp, Folder, Paperclip, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";

interface Props {
  onPickFiles: (files: File[]) => void;
  disabled: boolean;
  controls?: ReactNode;
  cwd?: string | null;
  workspace?: ReactNode;
  showStop: boolean;
  onStop?: () => void;
  canSend: boolean;
  onSend: () => void;
}

export function ComposerToolbar({
  onPickFiles,
  disabled,
  controls,
  cwd,
  workspace,
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
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
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
          </TooltipTrigger>
          <TooltipContent>{t("conversations.composer.attach")}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      {workspace ?? (cwd !== undefined ? <WorkingFolder cwd={cwd} /> : null)}
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

/** The folder the conversation runs in: fixed once it exists, so a plain chip. */
function WorkingFolder({ cwd }: { cwd: string | null }) {
  const { t } = useTranslation();
  const label = cwd ? abbreviateHomePath(cwd) : t("conversations.draft.workspace");
  return (
    <span
      data-testid="composer-folder"
      className="inline-flex h-control-sm min-w-0 max-w-[24rem] items-center gap-1.5 px-1.5 text-xs text-text-muted"
    >
      <Folder className="size-3.5 shrink-0" aria-hidden />
      <TruncatedText text={cwd ?? label} mono>
        {label}
      </TruncatedText>
    </span>
  );
}
