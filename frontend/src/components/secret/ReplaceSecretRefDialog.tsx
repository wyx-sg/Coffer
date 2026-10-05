// src/components/secret/ReplaceSecretRefDialog.tsx — replace the secret one resource field uses, in place.
//
// For a field with no dialog of its own (an MCP server's env var or header, a
// custom tool group's header): a new value is written into the secret it uses
// now (spec secret "Store a secret through the API"); another stored secret is
// handed to `onRebind`, which saves the resource pointing at it.
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
import { PasswordInput } from "@/components/ui/password-input";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useSetSecret } from "@/lib/hooks/useSecrets";
import { SecretNameLink, useSecretName } from "./SecretNameLink";
import { SecretSourceSwitch, type SecretSource } from "./SecretSourceSwitch";

interface Props {
  /** The ref the field uses now; null closes the dialog. */
  secretRef: string | null;
  /** What the field is called (an env var, a header) — the dialog's title. */
  field: string;
  onClose: () => void;
  /** Saves the resource pointing at `ref` instead. */
  onRebind: (ref: string) => Promise<unknown>;
}

const TERM = "text-xs font-label text-text";

export function ReplaceSecretRefDialog({ secretRef, field, onClose, onRebind }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const set = useSetSecret();
  const valueId = useId();
  const open = secretRef !== null;
  const name = useSecretName(secretRef ?? "");
  const [source, setSource] = useState<SecretSource>("value");
  const [value, setValue] = useState("");
  const [picked, setPicked] = useState("");
  const [rebindError, setRebindError] = useState<unknown>(null);
  const [rebinding, setRebinding] = useState(false);

  const { reset } = set;
  useEffect(() => {
    if (!open) return;
    setSource("value");
    setValue("");
    setPicked("");
    setRebindError(null);
    reset();
  }, [open, reset]);

  if (!secretRef) return null;
  const pending = set.isPending || rebinding;
  const ready = source === "value" ? value !== "" : picked !== "";
  const error = source === "value" ? set.error : rebindError;

  const submit = async () => {
    if (!ready || pending) return;
    if (source === "value") {
      try {
        await set.mutateAsync({ ref: secretRef, value });
      } catch {
        return; // shown inline
      }
      toast.success(t("secrets.replace.replaced", { name }));
      onClose();
      return;
    }
    setRebinding(true);
    setRebindError(null);
    try {
      await onRebind(picked);
      onClose();
    } catch (err) {
      setRebindError(err);
    } finally {
      setRebinding(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !pending && onClose()}>
      <DialogContent className="max-w-[480px]">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("secretRef.title", { field })}</DialogTitle>
            <DialogDescription className="sr-only">{t("secretRef.existingHint")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <span className={TERM}>{t("secretRef.current")}</span>
            <SecretNameLink secretRef={secretRef} className="text-xs" onNavigate={onClose} />
          </div>
          <SecretSourceSwitch
            source={source}
            onSourceChange={setSource}
            currentRef={secretRef}
            picked={picked}
            onPick={setPicked}
            disabled={pending}
          />
          {source === "value" ? (
            <div className="flex flex-col gap-1.5">
              <label htmlFor={valueId} className={TERM}>
                {t("secrets.replace.value")}
              </label>
              <PasswordInput
                id={valueId}
                value={value}
                autoComplete="off"
                autoFocus
                onChange={(e) => setValue(e.target.value)}
              />
              <p className="text-xs text-text-muted">{t("secrets.replace.hint")}</p>
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="text-xs text-danger">
              {translateApiError(t, error)}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!ready || pending}>
              {t(source === "value" ? "secrets.replace.submit" : "secretRef.useSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
