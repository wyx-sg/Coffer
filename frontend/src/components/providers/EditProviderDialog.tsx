// src/components/providers/EditProviderDialog.tsx — edit a provider's name and addresses; its key is only named.
//
// A changed NAME is the kind-agnostic rename (`PATCH /resources/{uid}`), sent
// FIRST so a taken label fails before anything else lands; nothing navigates,
// because the page is addressed by uid. The addresses are the OpenAI- and
// Anthropic-compatible ones (ADR one-connection-serves-both-wires); they are
// sent only when one moved. The wire they imply is locked while an agent runs
// on the provider (409 PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE), so adding or
// clearing the OpenAI address of a live connection is refused. The key is write-only and changed with Replace key, so
// here it is a read-only row. Failures render inline.
import { useEffect } from "react";
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
import { useUpdateProvider } from "@/lib/hooks/useProviders";
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
      secret_ref: provider.secret_ref,
    });
  };

  const failure = rename.error ?? update.error;
  const pending = rename.isPending || update.isPending;

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
          <KeyRefField secretRef={provider.secret_ref} />
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
