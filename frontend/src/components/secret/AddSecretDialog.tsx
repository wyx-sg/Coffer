// src/components/secret/AddSecretDialog.tsx — Add secret: a standalone secret under a minted id.
//
// The person gives a label, an optional description and a value; Coffer mints the id the secret is cited by
// (`coffer://secret/<id>`), which the dialog then shows with Copy and a Done button. The label can
// be changed later; the id never (spec secret "Mint every secret's id; a person names it").
// The value is never shown back.
import { useEffect, useId, useState } from "react";
import { Check, Copy } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { translateApiError } from "@/lib/api/errors";
import { useCopyText } from "@/lib/hooks/useCopyText";
import { useAddSecret } from "@/lib/hooks/useSecrets";
import { DESCRIPTION_MAX, LABEL_MAX } from "./secretRows";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const FIELD = "text-xs font-label text-text";

export function AddSecretDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const add = useAddSecret();
  const { copied, copy } = useCopyText();
  const labelId = useId();
  const descriptionId = useId();
  const valueId = useId();
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [value, setValue] = useState("");

  const { reset } = add;
  useEffect(() => {
    if (!open) return;
    setLabel("");
    setDescription("");
    setValue("");
    reset();
  }, [open, reset]);

  const canSubmit = label.trim() !== "" && value !== "" && !add.isPending;

  const submit = () => {
    if (!canSubmit) return;
    add.mutate({ label: label.trim(), value, description: description.trim() || undefined });
  };

  const added = add.data;
  return (
    <Dialog open={open} onOpenChange={(next) => !add.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-[480px]">
        {added ? (
          <div className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>{t("secrets.add.addedTitle", { name: label.trim() })}</DialogTitle>
              <DialogDescription>{t("secrets.add.addedHint")}</DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-1.5 rounded-md bg-surface-sunken px-3 py-2">
              <code className="min-w-0 flex-1 break-all font-mono text-xs text-text">
                {added.uri}
              </code>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("secrets.detail.copyReference")}
                onClick={() => copy(added.uri)}
              >
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              </Button>
            </div>
            <DialogFooter>
              <Button type="button" onClick={() => onOpenChange(false)}>
                {t("common.done")}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <DialogHeader>
              <DialogTitle>{t("secrets.add.title")}</DialogTitle>
              <DialogDescription className="sr-only">{t("secrets.subtitle")}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={labelId} className={FIELD}>
                {t("secrets.add.label")}
              </label>
              <Input
                id={labelId}
                value={label}
                maxLength={LABEL_MAX}
                autoComplete="off"
                placeholder={t("secrets.add.labelPlaceholder")}
                onChange={(e) => setLabel(e.target.value)}
              />
              <p className="text-xs text-text-muted">{t("secrets.add.labelHint")}</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={descriptionId} className={FIELD}>
                {t("secrets.detail.description")}
              </label>
              <Input
                id={descriptionId}
                value={description}
                maxLength={DESCRIPTION_MAX}
                autoComplete="off"
                placeholder={t("secrets.detail.descriptionPlaceholder")}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={valueId} className={FIELD}>
                {t("secrets.add.value")}
              </label>
              <PasswordInput
                id={valueId}
                value={value}
                autoComplete="off"
                onChange={(e) => setValue(e.target.value)}
              />
              <p className="text-xs text-text-muted">{t("secrets.add.valueHint")}</p>
            </div>
            {add.error ? (
              <p role="alert" className="text-xs text-danger">
                {translateApiError(t, add.error)}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {add.isPending ? t("secrets.add.submitting") : t("secrets.add.submit")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
