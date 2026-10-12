// src/components/providers/EditProviderDialog.tsx — edit a provider's name, addresses and key.
//
// A changed NAME is the kind-agnostic rename (`PATCH /resources/{uid}`), sent
// FIRST so a taken label fails before anything else lands; nothing navigates,
// because the page is addressed by uid. The addresses are the OpenAI- and
// Anthropic-compatible ones (ADR one-connection-serves-both-wires); they are
// sent only when one moved. The wire they imply is locked while an agent runs
// on the provider (409 PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE), so adding or
// clearing the OpenAI address of a live connection is refused. The key is
// write-only: its row names the secret, and Replace opens the same fields as the
// Replace key dialog in place — a new value PATCHes `secret_value` (the value
// behind the same ref is overwritten), another secret PATCHes `secret_ref` —
// sent LAST, after the name and addresses, with the same Save. Test uses the
// entered key when there is one. Failures render inline.
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Plug } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import type { Provider, ProviderPatch } from "@/lib/api/providers";
import {
  useRebindProviderKey,
  useReplaceProviderKey,
  useUpdateProvider,
} from "@/lib/hooks/useProviders";
import { draftReady, type ReplaceDraft } from "@/components/secret/ReplaceSecretFields";
import { useRenameResource } from "@/lib/hooks/useResourceMutations";
import { addressesOf, endpointOf, fieldsOf } from "@/lib/providers/addresses";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { AddressInputs } from "./AddressInputs";
import { FieldError } from "./FieldError";
import { KeyRefField } from "./KeyRefField";
import { ProbeResult } from "./ProbeResult";
import { editSchema, type EditValues } from "./providerSchemas";
import { useEndpointTest } from "./useEndpointTest";
import { useLockedBy } from "./useLockedBy";

interface Props {
  open: boolean;
  provider: Provider;
  use: ProviderUse;
  onClose: () => void;
  onSaved: () => void;
}

export function EditProviderDialog({ open, provider, use, onClose, onSaved }: Props) {
  const { t } = useTranslation();
  const update = useUpdateProvider();
  const rename = useRenameResource();
  const replaceValue = useReplaceProviderKey();
  const rebind = useRebindProviderKey();
  const [key, setKey] = useState<ReplaceDraft | null>(null);
  const test = useEndpointTest(t);
  const lockedBy = useLockedBy(use);
  const form = useForm<EditValues>({ resolver: zodResolver(editSchema(t)) });
  const { register, handleSubmit, reset, getValues, formState } = form;
  const initial = addressesOf(provider);

  useEffect(() => {
    if (!open) return;
    reset({ name: provider.name, openaiUrl: initial.openai, anthropicUrl: initial.anthropic });
    test.reset();
    update.reset();
    rename.reset();
    replaceValue.reset();
    rebind.reset();
    setKey(null);
    // Re-seed only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = handleSubmit(async (v) => {
    const name = v.name.trim();
    const patch: ProviderPatch = {};
    const moved =
      v.openaiUrl.trim() !== initial.openai.trim() ||
      v.anthropicUrl.trim() !== initial.anthropic.trim();
    const endpoint = endpointOf({ openai: v.openaiUrl, anthropic: v.anthropicUrl });
    if (moved && endpoint) {
      patch.base_url = endpoint.baseUrl;
      // "" clears a second address the connection had.
      patch.anthropic_base_url = endpoint.anthropicBaseUrl ?? "";
      if (endpoint.protocol !== provider.protocol) patch.protocol = endpoint.protocol;
    }
    try {
      if (name !== provider.name)
        await rename.mutateAsync({ kind: "provider", uid: provider.uid, name });
      if (Object.keys(patch).length > 0) await update.mutateAsync({ uid: provider.uid, patch });
      // An empty replacement keeps the key as it is.
      if (key && draftReady(key)) {
        if (key.source === "value")
          await replaceValue.mutateAsync({ uid: provider.uid, secret: key.value });
        else await rebind.mutateAsync({ uid: provider.uid, secretRef: key.picked });
      }
    } catch {
      return; // the failure is the mutation's state, rendered below
    }
    onSaved();
    onClose();
  });

  const runTest = () => {
    const v = getValues();
    const endpoint = endpointOf({ openai: v.openaiUrl, anthropic: v.anthropicUrl });
    if (!endpoint) return;
    void test.run({
      provider: endpoint.protocol,
      base_url: endpoint.baseUrl,
      ...(key?.source === "value" && key.value
        ? { secret_value: key.value }
        : {
            secret_ref: key?.source === "existing" && key.picked ? key.picked : provider.secret_ref,
          }),
    });
  };

  const failure = rename.error ?? update.error ?? replaceValue.error ?? rebind.error;
  const pending =
    rename.isPending || update.isPending || replaceValue.isPending || rebind.isPending;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent aria-describedby={undefined} className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("providers.edit.title", { name: provider.name })}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={save} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pe-name" required>
              {t("providers.fields.name")}
            </Label>
            <Input id="pe-name" aria-describedby="pe-name-error" {...register("name")} />
            <FieldError id="pe-name-error" message={formState.errors.name?.message} />
            <p className="text-xs text-text-muted">{t("resources.freeName.hint")}</p>
          </div>
          <AddressInputs
            idPrefix="pe"
            show={fieldsOf(provider)}
            openai={register("openaiUrl")}
            anthropic={register("anthropicUrl")}
            errors={{
              openai: formState.errors.openaiUrl?.message,
              anthropic: formState.errors.anthropicUrl?.message,
            }}
            hint
          />
          {lockedBy ? (
            <p className="-mt-2 text-xs text-text-muted">
              {t("providers.edit.locked", { agents: lockedBy })}
            </p>
          ) : null}
          <KeyRefField
            secretRef={provider.secret_ref}
            draft={key}
            onDraftChange={(next) => {
              setKey(next);
              test.reset();
            }}
            disabled={pending}
          />
          <ProbeResult
            result={test.result}
            pending={test.isPending}
            okNote={(count) => t("providers.test.editOk", { count })}
            failNote={t("providers.test.editFail")}
          />
          {failure != null ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, failure)}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" className="sm:mr-auto" onClick={runTest}>
              <Plug aria-hidden /> {t("providers.actions.test")}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? t("common.saving") : t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
