// frontend/src/components/channel/ChannelSystemPromptsDialog.tsx
// Edit a channel's two system prompts — one for direct chats, one for group
// chats — in one dialog. Each is plain multi-line text up to the daemon's cap;
// an empty one adds nothing to a turn. The dialog closes only once the save
// has landed, so a refused save stays open with what was typed.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SYSTEM_PROMPT_MAX } from "@/lib/channels/editChannel";
import { cn } from "@/lib/utils";
import { FieldError } from "./FieldError";

/** The two prompts, as the dialog edits them. */
interface SystemPrompts {
  direct: string;
  group: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The stored prompts — what the fields start from each time it opens. */
  prompts: SystemPrompts;
  /** Save both; resolves to whether the save landed. */
  onSave: (prompts: SystemPrompts) => Promise<boolean>;
}

export function ChannelSystemPromptsDialog({ open, onOpenChange, prompts, onSave }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(prompts);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (open) setDraft(prompts);
    // Reset only on opening: a refetch while open must not wipe what is typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const tooLong = draft.direct.length > SYSTEM_PROMPT_MAX || draft.group.length > SYSTEM_PROMPT_MAX;

  const save = async () => {
    setSaving(true);
    const saved = await onSave({ direct: draft.direct.trim(), group: draft.group.trim() });
    setSaving(false);
    if (saved) onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[640px]">
        <DialogHeader>
          <DialogTitle>{t("channels.settings.prompts.dialogTitle")}</DialogTitle>
          <DialogDescription>{t("channels.settings.prompts.dialogDescription")}</DialogDescription>
        </DialogHeader>
        <PromptField
          label={t("channels.settings.prompts.direct")}
          hint={t("channels.settings.prompts.directHint")}
          value={draft.direct}
          onChange={(direct) => setDraft((d) => ({ ...d, direct }))}
        />
        <PromptField
          label={t("channels.settings.prompts.group")}
          hint={t("channels.settings.prompts.groupHint")}
          value={draft.group}
          onChange={(group) => setDraft((d) => ({ ...d, group }))}
        />
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={saving || tooLong} onClick={() => void save()}>
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PromptField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const over = value.length > SYSTEM_PROMPT_MAX;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea
        id={id}
        rows={6}
        value={value}
        aria-describedby={`${id}-hint`}
        aria-invalid={over ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="flex items-start justify-between gap-3 text-xs text-text-muted">
        <span id={`${id}-hint`}>{hint}</span>
        <span className={cn("shrink-0", over && "text-danger")}>
          {t("channels.settings.prompts.count", { count: value.length, max: SYSTEM_PROMPT_MAX })}
        </span>
      </div>
      <FieldError
        id={`${id}-error`}
        message={
          over ? t("channels.settings.prompts.tooLong", { max: SYSTEM_PROMPT_MAX }) : undefined
        }
      />
    </div>
  );
}
