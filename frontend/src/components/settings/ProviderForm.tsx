// components/settings/ProviderForm.tsx — add / edit an LLM connection (spec 011).
// A connection = endpoint + key + (detected) protocol. The model lives apart
// from the connection (amendment E1/E3) — it is chosen at the point of use, so
// the dialog has no model field. The protocol is not hand-picked: after base_url
// + key are entered the dialog detects it (E2); only an inconclusive probe falls
// back to a manual pick. In edit mode (`initial` set) name + protocol are fixed
// and the secret is optional — left blank, the stored key is kept.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { useDetectProtocol } from "@/lib/hooks/useModelIntrospection";
import { translateApiError } from "@/lib/api/errors";
import {
  wireNeedsCredential,
  type Protocol,
  type Provider,
  type ProviderCreate,
  type ProviderPatch,
} from "@/lib/api/providers";

interface Props {
  /** Present → edit an existing connection (name + protocol locked, secret optional). */
  initial?: Provider;
  submitError?: unknown;
  pending: boolean;
  onSubmit: (values: ProviderCreate) => Promise<void> | void;
  /** Required when `initial` is set; receives the PATCH body. */
  onUpdate?: (patch: ProviderPatch) => Promise<void> | void;
  onCancel: () => void;
}

export function ProviderForm({ initial, submitError, pending, onSubmit, onUpdate, onCancel }: Props) {
  const { t } = useTranslation();
  const isEdit = initial != null;
  const [name, setName] = useState(initial?.name ?? "");
  // "" until detected (create mode); edit mode keeps the locked protocol.
  const [protocol, setProtocol] = useState<Protocol | "">(initial?.protocol ?? "");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [secret, setSecret] = useState("");
  // Shown only when detection is inconclusive (`unknown`) — the honest fallback.
  const [manualPick, setManualPick] = useState(false);

  const detect = useDetectProtocol();
  // Before a protocol is known, assume a key is needed (so the field is available
  // to detect with); ollama clears it once detected.
  const needsCredential = protocol === "" || wireNeedsCredential(protocol);

  const runDetect = () => {
    if (isEdit || !baseUrl) return;
    detect.mutate(
      { base_url: baseUrl, secret_value: secret || null },
      {
        onSuccess: (r) => {
          if (r.protocol === "unknown") {
            setManualPick(true);
          } else {
            setProtocol(r.protocol as Protocol);
            setManualPick(false);
          }
        },
      },
    );
  };

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (isEdit) {
          const patch: ProviderPatch = { base_url: baseUrl };
          if (needsCredential && secret) patch.secret_value = secret;
          await onUpdate?.(patch);
          return;
        }
        if (!protocol) return; // guard: protocol must be known before create
        const values: ProviderCreate = { name, protocol, base_url: baseUrl };
        if (needsCredential && secret) values.secret_value = secret;
        await onSubmit(values);
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="p-name">{t("settings.connections.name")}</Label>
        <Input
          id="p-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          disabled={isEdit}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-base">{t("settings.connections.baseUrl")}</Label>
        <Input
          id="p-base"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          onBlur={runDetect}
          required
        />
      </div>
      {needsCredential && (
        <div className="space-y-1.5">
          <Label htmlFor="p-secret">{t("settings.connections.secret")}</Label>
          <PasswordInput
            id="p-secret"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            onBlur={runDetect}
            required={!isEdit}
            placeholder={isEdit ? t("settings.connections.secretKeepBlank") : undefined}
          />
        </div>
      )}
      {/* Protocol is detected, not hand-picked. Edit mode shows the locked value;
          create mode shows the detected one, or a manual fallback when inconclusive. */}
      <div className="space-y-1.5">
        <Label htmlFor="p-wire">{t("settings.connections.wireFormat")}</Label>
        {isEdit ? (
          <p className="text-sm text-muted-foreground">{initial?.protocol}</p>
        ) : manualPick ? (
          <select
            id="p-wire"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as Protocol)}
          >
            <option value="" disabled>
              {t("settings.connections.detectFailed")}
            </option>
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
            <option value="ollama">ollama</option>
          </select>
        ) : (
          <div className="flex items-center gap-2 text-sm">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={runDetect}
              disabled={!baseUrl || detect.isPending}
            >
              {detect.isPending && <Loader2 className="mr-1 size-3.5 animate-spin" />}
              {t("settings.connections.detectType")}
            </Button>
            {protocol && (
              <span className="flex items-center gap-1 text-green-600" role="status">
                <CheckCircle2 className="size-3.5" />
                {t("settings.connections.detected", { wire: protocol })}
              </span>
            )}
          </div>
        )}
      </div>
      {submitError != null && (
        <p className="text-sm text-destructive">{translateApiError(t, submitError)}</p>
      )}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={pending || (!isEdit && !protocol)}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
