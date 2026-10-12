// frontend/src/components/channel/ChannelSystemPromptsDialog.tsx
// Rewrite a channel's two reply styles — one for direct chats, one for group
// chats — in one dialog. Each starts from the style in force (the owner's, or
// Coffer's default) and has Restore default beside it; a style saved equal to
// the default keeps following Coffer's default as it changes. Coffer's channel
// note is not here: it is not the owner's to edit. The dialog closes only once
// the save has landed, so a refused save stays open with what was typed.
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
import { REPLY_STYLE_MAX } from "@/lib/channels/editChannel";
import { cn } from "@/lib/utils";
import { FieldError } from "./FieldError";

/** The two reply styles, as the dialog edits them. */
export interface ReplyStyles {
  direct: string;
  group: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The styles in force — what the fields start from each time it opens. */
  styles: ReplyStyles;
  /** Coffer's defaults, for Restore default; null when unknown. */
  defaults: ReplyStyles | null;
  /** Save both; resolves to whether the save landed. A style equal to the
   *  default is sent as "", so it follows the default. */
  onSave: (styles: ReplyStyles) => Promise<boolean>;
}

const KINDS = ["direct", "group"] as const;

export function ChannelSystemPromptsDialog({
  open,
  onOpenChange,
  styles,
  defaults,
  onSave,
}: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(styles);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (open) setDraft(styles);
    // Reset only on opening: a refetch while open must not wipe what is typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const tooLong = KINDS.some((kind) => draft[kind].length > REPLY_STYLE_MAX);

  const save = async () => {
    const settle = (kind: (typeof KINDS)[number]) => {
      const text = draft[kind].trim();
      return defaults && text === defaults[kind].trim() ? "" : text;
    };
    setSaving(true);
    const saved = await onSave({ direct: settle("direct"), group: settle("group") });
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
        {KINDS.map((kind) => (
          <StyleField
            key={kind}
            label={t(`channels.settings.prompts.${kind}`)}
            hint={t(`channels.settings.prompts.${kind}Hint`)}
            value={draft[kind]}
            defaultValue={defaults?.[kind] ?? null}
            onChange={(value) => setDraft((d) => ({ ...d, [kind]: value }))}
          />
        ))}
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

function StyleField({
  label,
  hint,
  value,
  defaultValue,
  onChange,
}: {
  label: string;
  hint: string;
  value: string;
  defaultValue: string | null;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const over = value.length > REPLY_STYLE_MAX;
  const isDefault = defaultValue !== null && value.trim() === defaultValue.trim();
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>{label}</Label>
        {defaultValue !== null ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={isDefault}
            aria-label={t("channels.settings.prompts.restoreAria", { kind: label })}
            onClick={() => onChange(defaultValue)}
          >
            {t("channels.settings.prompts.restore")}
          </Button>
        ) : null}
      </div>
      <Textarea
        id={id}
        rows={7}
        value={value}
        aria-describedby={`${id}-hint`}
        aria-invalid={over ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="flex items-start justify-between gap-3 text-xs text-text-muted">
        <span id={`${id}-hint`}>{hint}</span>
        <span className={cn("shrink-0", over && "text-danger")}>
          {t("channels.settings.prompts.count", { count: value.length, max: REPLY_STYLE_MAX })}
        </span>
      </div>
      <FieldError
        id={`${id}-error`}
        message={
          over ? t("channels.settings.prompts.tooLong", { max: REPLY_STYLE_MAX }) : undefined
        }
      />
    </div>
  );
}
