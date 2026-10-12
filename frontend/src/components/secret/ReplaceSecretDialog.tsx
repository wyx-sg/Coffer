// src/components/secret/ReplaceSecretDialog.tsx — Replace {field}: the one dialog that replaces a secret a field uses.
//
// Every "Replace key…" opens it — a provider's API key, a channel's token, an MCP
// server's variable or header, a tool group's header, a secret menu's "Change
// value…" and the missing-secret banners — with the fields every Edit dialog's
// inline Replace shows too (ReplaceSecretFields). A new value is written into the
// secret the field uses now (spec secret "Store a secret through the API") unless
// the caller writes it its own way (a provider's key, a channel's token); another
// stored secret is handed to `onRebind`, which saves the resource pointing at it.
// A secret missing on this Mac reads Add instead of Replace (spec secret "Show a
// secret this Mac cannot open as missing on this Mac").
import { useEffect, useState, type ReactNode } from "react";
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
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useSecrets, useSetSecret } from "@/lib/hooks/useSecrets";
import {
  draftReady,
  EMPTY_DRAFT,
  ReplaceSecretFields,
  type ReplaceDraft,
} from "./ReplaceSecretFields";
import { useSecretName } from "./SecretNameLink";
import { isMissingHere } from "./secretRows";

interface Props {
  /** The ref the field uses now; null closes the dialog. */
  secretRef: string | null;
  onClose: () => void;
  /** What the field is called (API key, Bot token, an env var) — the title. The secret's name by default. */
  field?: string;
  /** A sentence under the title. */
  description?: string;
  /** The value field's label. */
  valueLabel?: string;
  /** Saves the resource pointing at another stored secret; omitted, only a new value is offered. */
  onRebind?: (ref: string) => Promise<unknown>;
  /** Writes the new value the resource's own way; omitted, it is stored under `secretRef`. */
  onReplaceValue?: (value: string) => Promise<unknown>;
  /** Controlled draft, for a caller that checks the value as it is typed. */
  draft?: ReplaceDraft;
  onDraftChange?: (draft: ReplaceDraft) => void;
  /** The check under the value field, and whether it blocks Replace (a rejected key). */
  check?: ReactNode;
  blocked?: boolean;
}

export function ReplaceSecretDialog({
  secretRef,
  onClose,
  field,
  description,
  valueLabel,
  onRebind,
  onReplaceValue,
  draft: controlled,
  onDraftChange,
  check,
  blocked = false,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const set = useSetSecret();
  const { data } = useSecrets();
  const name = useSecretName(secretRef ?? "");
  const open = secretRef !== null;
  const [own, setOwn] = useState<ReplaceDraft>(EMPTY_DRAFT);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const draft = controlled ?? own;
  const setDraft = (next: ReplaceDraft) => {
    setError(null);
    if (onDraftChange) onDraftChange(next);
    else setOwn(next);
  };

  useEffect(() => {
    if (!open) return;
    setOwn(EMPTY_DRAFT);
    onDraftChange?.(EMPTY_DRAFT);
    setError(null);
    setPending(false);
    // Re-seed only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!secretRef) return null;
  const row = data?.refs.find((r) => r.ref === secretRef);
  const adding = row === undefined ? data !== undefined : isMissingHere(row);
  const source = onRebind ? draft.source : "value";
  const ready = draftReady({ ...draft, source }) && !(source === "value" && blocked);
  const label = field ?? name;

  const submit = async () => {
    if (!ready || pending) return;
    setPending(true);
    setError(null);
    try {
      if (source === "existing" && onRebind) {
        await onRebind(draft.picked);
      } else if (onReplaceValue) {
        await onReplaceValue(draft.value);
      } else {
        await set.mutateAsync({ ref: secretRef, value: draft.value });
        toast.success(t(adding ? "secretRef.added" : "secretRef.replaced", { name }));
      }
    } catch (err) {
      setError(err);
      setPending(false);
      return;
    }
    setPending(false);
    onClose();
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
            <DialogTitle>
              {t(adding ? "secretRef.addTitle" : "secretRef.title", { field: label })}
            </DialogTitle>
            {description ? (
              <DialogDescription>{description}</DialogDescription>
            ) : (
              <DialogDescription className="sr-only">{t("secretRef.valueHint")}</DialogDescription>
            )}
          </DialogHeader>
          <ReplaceSecretFields
            currentRef={secretRef}
            draft={draft}
            onChange={setDraft}
            allowExisting={onRebind !== undefined}
            valueLabel={valueLabel}
            check={check}
            defaultNewLabel={label}
            disabled={pending}
            autoFocus
            onNavigate={onClose}
          />
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
              {pending
                ? t("common.saving")
                : source === "existing"
                  ? t("secretRef.useSubmit")
                  : t(adding ? "secretRef.addSubmit" : "secretRef.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
