// src/components/chat/DraftWorkspacePicker.tsx — the folder chip in the draft's
// header, as a picker: Coffer's own workspace, the folders recent conversations
// started in, and one row for any other folder — a field to type or paste a
// path, whose one button is "Choose…" (the host's native dialog, or the in-app
// folder browser) while it is empty and "Use" once it holds a path. The path is cut with an
// ellipsis in the chip and whole in its tooltip. Only the draft has it: once the
// first message is sent the folder is fixed.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Folder } from "lucide-react";

import { FolderPicker } from "@/components/FolderPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { abbreviateHomePath } from "@/lib/agents/display";
import { readRecentWorkingDirs } from "@/lib/conversations/draftMemory";
import { cn } from "@/lib/utils";

interface Props {
  /** The folder the first turn will run in; null is Coffer's own workspace. */
  cwd: string | null;
  onChange: (cwd: string | null) => void;
}

export function DraftWorkspacePicker({ cwd, onChange }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const label = cwd ? abbreviateHomePath(cwd) : t("conversations.draft.workspace");
  const recent = open ? readRecentWorkingDirs() : [];

  const choose = (next: string | null) => {
    onChange(next);
    setOpen(false);
  };
  const submitTyped = () => {
    const path = typed.trim();
    if (!path) return;
    setTyped("");
    choose(path);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={t("conversations.draft.workspacePicker.label")}
                className="inline-flex min-w-0 max-w-[24rem] items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-text-muted outline-none transition-colors duration-fast hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-focus-ring"
              >
                <Folder className="size-3.5 shrink-0" aria-hidden />
                <span className="truncate font-mono">{label}</span>
                <ChevronDown className="size-3.5 shrink-0" aria-hidden />
              </button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent className="max-w-[420px] break-all">
            {cwd ?? t("conversations.draft.workspaceFull")}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <PopoverContent
        className="w-[320px] space-y-2 p-2"
        // The in-app folder browser is a dialog opened from here; clicking in
        // it must not count as clicking away from this popover.
        onInteractOutside={(e) => {
          if ((e.target as HTMLElement | null)?.closest?.('[role="dialog"]')) e.preventDefault();
        }}
      >
        <ul className="space-y-0.5" aria-label={t("conversations.draft.workspacePicker.label")}>
          <WorkspaceRow
            selected={cwd === null}
            onSelect={() => choose(null)}
            title={t("conversations.draft.workspaceFull")}
          >
            {t("conversations.draft.workspace")}
          </WorkspaceRow>
          {recent.map((dir) => (
            <WorkspaceRow key={dir} selected={cwd === dir} onSelect={() => choose(dir)} title={dir}>
              <span className="font-mono">{abbreviateHomePath(dir)}</span>
            </WorkspaceRow>
          ))}
        </ul>
        {/* One row for any other folder: type or paste a path and Use it, or
            leave the field empty and Choose… one. */}
        <form
          className="flex items-center gap-1.5 border-t border-border-subtle pt-2"
          onSubmit={(e) => {
            e.preventDefault();
            submitTyped();
          }}
        >
          <Input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            aria-label={t("conversations.draft.workspacePicker.typePath")}
            placeholder={t("conversations.draft.workspacePicker.typePath")}
            className="min-w-0 font-mono text-xs"
          />
          {typed.trim() ? (
            <Button type="submit" variant="outline" className="shrink-0">
              {t("conversations.draft.workspacePicker.use")}
            </Button>
          ) : (
            <FolderPicker
              value={cwd}
              onChange={choose}
              label={t("conversations.draft.workspacePicker.choose")}
            />
          )}
        </form>
      </PopoverContent>
    </Popover>
  );
}

function WorkspaceRow({
  selected,
  onSelect,
  title,
  children,
}: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li>
      <button
        type="button"
        title={title}
        aria-current={selected ? "true" : undefined}
        onClick={onSelect}
        className={cn(
          "flex h-control-md w-full items-center gap-2 rounded-md px-2 text-left text-xs text-text outline-none",
          "transition-colors duration-fast hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-focus-ring",
        )}
      >
        <span className="min-w-0 flex-1 truncate">{children}</span>
        {selected ? <Check className="size-3.5 shrink-0" aria-hidden /> : null}
      </button>
    </li>
  );
}
