// src/components/secret/NewSecretDialog.tsx — New secret…: the small dialog a secret field's menu opens.
// Label + value → stored under an id Coffer mints → the caller selects it (by that id). A person
// never types the id.
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
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useAddSecret } from "@/lib/hooks/useSecrets";
import { LABEL_MAX, standaloneName } from "./secretRows";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The label the dialog opens with. */
  defaultLabel?: string;
  /** The secret now exists: select it by its minted id. */
  onCreated: (name: string) => void;
}

const LABEL = "text-xs font-label text-text";

export function NewSecretDialog({ open, onOpenChange, defaultLabel = "", onCreated }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const add = useAddSecret();
  const labelId = useId();
  const valueId = useId();
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");

  const { reset } = add;
  useEffect(() => {
    if (!open) return;
    setLabel(defaultLabel);
    setValue("");
    reset();
  }, [open, defaultLabel, reset]);

  const trimmed = label.trim();
  const canSubmit = trimmed !== "" && value !== "" && !add.isPending;

  const submit = async () => {
    if (!canSubmit) return;
    try {
      const added = await add.mutateAsync({ label: trimmed, value });
      toast.success(t("secrets.add.added", { name: trimmed }));
      onCreated(standaloneName(added.ref) ?? added.ref);
      onOpenChange(false);
    } catch {
      // Shown inline from the mutation's error.
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !add.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-[480px]">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("secretField.dialog.title")}</DialogTitle>
            <DialogDescription className="sr-only">{t("secrets.subtitle")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={labelId} className={LABEL}>
              {t("secrets.add.label")}
            </label>
            <Input
              id={labelId}
              value={label}
              maxLength={LABEL_MAX}
              autoComplete="off"
              onChange={(e) => setLabel(e.target.value)}
            />
            <p className="text-xs text-text-muted">{t("secrets.add.labelHint")}</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={valueId} className={LABEL}>
              {t("secrets.add.value")}
            </label>
            <Input
              id={valueId}
              type="password"
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
              {add.isPending
                ? t("secrets.add.submitting")
                : add.error
                  ? t("common.retry")
                  : t("secrets.add.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
