// src/components/providers/EditProviderDialog.tsx — edit a provider's name, protocol and base URL; its key is only named.
//
// A changed NAME is the kind-agnostic rename (`PATCH /resources/{uid}`), sent
// FIRST so a taken label fails before anything else lands; nothing navigates,
// because the page is addressed by uid. The protocol is locked while an agent
// runs on the provider (409 PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE) and is sent
// only when it moved. The key is write-only and changed with Replace key, so
// here it is a read-only row. Failures render inline.
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import type { Protocol, Provider, ProviderPatch } from "@/lib/api/providers";
import { useUpdateProvider } from "@/lib/hooks/useProviders";
import { useRenameResource } from "@/lib/hooks/useResourceMutations";
import { EDITABLE_PROTOCOLS, PROTOCOL_LABEL_KEY } from "@/lib/providers/presets";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { displayName } from "@/lib/resourceTitle";
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
  const lockedBy = useLockedBy(provider, use);
  const form = useForm<EditValues>({ resolver: zodResolver(editSchema(t)) });
  const { register, control, handleSubmit, reset, getValues, formState } = form;

  useEffect(() => {
    if (!open) return;
    reset({ name: provider.name, protocol: provider.protocol, baseUrl: provider.base_url });
    test.reset();
    update.reset();
    rename.reset();
    // Re-seed only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const protocols: readonly Protocol[] = EDITABLE_PROTOCOLS.includes(provider.protocol)
    ? EDITABLE_PROTOCOLS
    : [...EDITABLE_PROTOCOLS, provider.protocol];

  const save = handleSubmit(async (v) => {
    const name = v.name.trim();
    const patch: ProviderPatch = { base_url: v.baseUrl.trim() };
    if (v.protocol !== provider.protocol) patch.protocol = v.protocol;
    try {
      if (name !== provider.name)
        await rename.mutateAsync({ kind: "provider", uid: provider.uid, name });
      await update.mutateAsync({ uid: provider.uid, patch });
    } catch {
      return; // the failure is the mutation's state, rendered below
    }
    onSaved();
    onClose();
  });

  const runTest = () => {
    const v = getValues();
    void test.run({
      provider: v.protocol,
      base_url: v.baseUrl.trim(),
      secret_ref: provider.secret_ref,
    });
  };

  const failure = rename.error ?? update.error;
  const pending = rename.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent aria-describedby={undefined} className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t("providers.edit.title", { name: displayName(provider) })}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={save} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pe-name" required>
              {t("providers.fields.name")}
            </Label>
            <Input id="pe-name" aria-describedby="pe-name-error" {...register("name")} />
            <FieldError id="pe-name-error" message={formState.errors.name?.message} />
            <p className="text-xs text-text-muted">{t("providers.edit.renameHint")}</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pe-protocol">{t("providers.fields.protocol")}</Label>
            <Controller
              control={control}
              name="protocol"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange} disabled={!!lockedBy}>
                  <SelectTrigger id="pe-protocol">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {protocols.map((p) => (
                      <SelectItem key={p} value={p}>
                        {t(PROTOCOL_LABEL_KEY[p])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {lockedBy ? (
              <p className="text-xs text-text-muted">
                {t("providers.edit.locked", { agents: lockedBy })}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pe-base" required>
              {t("providers.fields.baseUrl")}
            </Label>
            <Input
              id="pe-base"
              inputMode="url"
              className="font-mono text-xs"
              aria-describedby="pe-base-error"
              {...register("baseUrl")}
            />
            <FieldError id="pe-base-error" message={formState.errors.baseUrl?.message} />
          </div>
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
