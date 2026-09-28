// components/settings/ProviderForm.tsx — add / edit an LLM connection (spec provider-switching).
// A connection = endpoint + key + protocol. The model lives apart from the
// connection (spec provider-switching "Take projected model keys from the
// agent's binding") — chosen at the point of use — so the dialog has no model
// field. On create the user picks a PROVIDER preset (OpenAI, Anthropic,
// Google Gemini, Ollama, …) which fills the endpoint + protocol; "Custom" lets
// them enter any OpenAI-/Anthropic-compatible endpoint and pick the protocol by
// hand. In edit mode (`initial` set) the secret is optional — left blank, the
// stored key is kept.
//
// Validation is react-hook-form + the zod schema in providerFormSchema.ts, so
// every message under a field is translated and the endpoint is checked to be
// a full URL before anything is sent — the browser's own `required` bubbles
// could do neither.
//
// WHICH AGENTS the connection reaches is NOT a field here: the axis is the
// resource's framework-level per-agent SCOPE (ADR per-agent-resource-scope),
// owned by the shared `ScopeControl` that the connection's table row and its
// detail header render. A new connection starts on its wire's default scope
// (`Kind.default_scope`); the hint below says where to change it.
//
// The NAME is editable in edit mode, but it does NOT travel in the PATCH body:
// it is the connection's identity, not one of its settings, so it leaves as its
// own rename call — `onUpdate` hands the caller the new name alongside the
// patch and the caller sequences the two. That ordering is what makes a name
// collision fail before anything else has been written.
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { translateApiError } from "@/lib/api/errors";
import { titlePatchValue } from "@/lib/resourceTitle";
import { ResourceTitleField } from "@/components/resource/ResourceTitleField";
import {
  wireNeedsCredential,
  type Provider,
  type ProviderCreate,
  type ProviderPatch,
} from "@/lib/api/providers";
import { PRESETS } from "./connectionPresets";
import { providerFormSchema, type ProviderFormValues } from "./providerFormSchema";
import { PresetPicker, ProtocolPicker, REQUIRED } from "./ProviderWireFields";

interface Props {
  /** Present → edit an existing connection (the wire IS editable — see the
   *  picker below — and the secret is optional: blank keeps the stored key). */
  initial?: Provider;
  submitError?: unknown;
  pending: boolean;
  onSubmit: (values: ProviderCreate) => Promise<void> | void;
  /** Required when `initial` is set. Receives the PATCH body plus, when the user
   *  changed it, the new NAME — which is a separate rename call, not a patch
   *  field. `null` means the name is unchanged. `newTitle` is the title to set
   *  (`null` clears it), or `undefined` when the title is unchanged. */
  onUpdate?: (
    patch: ProviderPatch,
    newName: string | null,
    newTitle?: string | null,
  ) => Promise<void> | void;
  onCancel: () => void;
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-destructive" role="alert">
      {message}
    </p>
  );
}

export function ProviderForm({
  initial,
  submitError,
  pending,
  onSubmit,
  onUpdate,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const isEdit = initial != null;
  const form = useForm<ProviderFormValues>({
    resolver: zodResolver(providerFormSchema(t, { isEdit })),
    defaultValues: {
      name: initial?.name ?? "",
      title: initial?.title ?? "",
      presetId: "openai",
      protocol: initial?.protocol ?? "openai",
      baseUrl: initial?.base_url ?? "https://api.openai.com/v1",
      secret: "",
    },
  });
  const { register, control, watch, setValue, handleSubmit, formState } = form;
  const { errors } = formState;

  const presetId = watch("presetId");
  const protocol = watch("protocol");
  const isCustom = presetId === "custom";
  const needsCredential = wireNeedsCredential(protocol);

  // Picking a preset fills protocol + endpoint; custom clears the endpoint for
  // hand entry.
  const pickPreset = (id: string) => {
    setValue("presetId", id);
    const preset = PRESETS.find((p) => p.id === id);
    setValue("protocol", id === "custom" ? "openai" : preset?.protocol || "openai");
    setValue("baseUrl", id === "custom" ? "" : (preset?.baseUrl ?? ""), { shouldValidate: false });
  };

  const submit = handleSubmit(async (values) => {
    const baseUrl = values.baseUrl.trim();
    if (isEdit) {
      const patch: ProviderPatch = { base_url: baseUrl };
      if (values.protocol !== initial.protocol) patch.protocol = values.protocol;
      if (needsCredential && values.secret) patch.secret_value = values.secret;
      const renamed = values.name.trim();
      const nextTitle = titlePatchValue(values.title);
      await onUpdate?.(
        patch,
        renamed && renamed !== initial.name ? renamed : null,
        nextTitle !== (initial.title ?? null) ? nextTitle : undefined,
      );
      return;
    }
    const body: ProviderCreate = {
      name: values.name.trim(),
      protocol: values.protocol,
      base_url: baseUrl,
    };
    if (needsCredential && values.secret) body.secret_value = values.secret;
    await onSubmit(body);
  });

  return (
    <form className="space-y-3" onSubmit={submit} noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="p-name" className={REQUIRED}>
          {t("settings.connections.name")}
        </Label>
        <Input id="p-name" aria-describedby="p-name-error" {...register("name")} />
        <FieldError id="p-name-error" message={errors.name?.message} />
        {isEdit ? (
          <p className="text-xs text-muted-foreground">{t("settings.connections.renameHint")}</p>
        ) : null}
      </div>

      {isEdit ? (
        <Controller
          control={control}
          name="title"
          render={({ field }) => (
            <ResourceTitleField
              id="p-title"
              value={field.value}
              onChange={field.onChange}
              name={initial.name}
            />
          )}
        />
      ) : null}

      {/* Provider preset (create only). In edit mode the wire itself is
          editable instead: a wrong guess is corrected here rather than
          re-entered, key and all. The daemon refuses that CHANGE while the
          connection is switched on (409 PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE)
          — the wire decides which agents it covers and which `builtin`
          reverts — so `submit` sends `protocol` only when it actually moved. */}
      {isEdit ? (
        <ProtocolPicker id="p-wire-edit" control={control} />
      ) : (
        <PresetPicker value={presetId} onChange={pickPreset} />
      )}

      {/* Custom connections pick the protocol by hand. */}
      {!isEdit && isCustom ? <ProtocolPicker id="p-wire" control={control} /> : null}

      <div className="space-y-1.5">
        <Label htmlFor="p-base" className={REQUIRED}>
          {t("settings.connections.baseUrl")}
        </Label>
        <Input
          id="p-base"
          inputMode="url"
          aria-describedby="p-base-error"
          {...register("baseUrl")}
        />
        <FieldError id="p-base-error" message={errors.baseUrl?.message} />
      </div>

      {needsCredential && (
        <div className="space-y-1.5">
          <Label htmlFor="p-secret" className={isEdit ? undefined : REQUIRED}>
            {t("settings.connections.secret")}
          </Label>
          <PasswordInput
            id="p-secret"
            aria-describedby="p-secret-error"
            placeholder={isEdit ? t("common.secretKeepBlank") : undefined}
            {...register("secret")}
          />
          <FieldError id="p-secret-error" message={errors.secret?.message} />
        </div>
      )}

      {/* Reach lives on the resource's scope, not in this dialog — the row's and
          the detail header's ScopeControl own it. Said here so the control's
          absence reads as a pointer rather than a missing field. */}
      <p className="text-xs text-muted-foreground">{t("settings.connections.reachHint")}</p>

      {submitError != null && (
        <p className="text-sm text-destructive">{translateApiError(t, submitError)}</p>
      )}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={pending}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
