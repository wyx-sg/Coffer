// src/components/providers/ProviderEndpoint.tsx — the Endpoint section: protocol, runtime, base URL and the API key's secret.
//
// The key is never shown — only the secret reference it is stored under
// (`secret:` + ref), write-only, with Replace key. A replaced key that is in
// use waits for approval in the Coffer app before it takes effect (spec
// secret "Hold a replaced value in use until a person approves it"), so
// while that approval is pending the row says so and offers Review. The
// protocol is locked while an agent runs on the provider (spec
// provider-switching "Refuse to move the wire of a live connection"). Route
// says agents reach it through Coffer's proxy; Fallback is "Use as fallback
// for other providers" (spec provider-switching "Order providers, and fail over
// in that order"), which a local runtime never is.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound, Lock } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { TruncatedText } from "@/components/ui/truncated-text";
import { Switch } from "@/components/ui/switch";
import type { Provider } from "@/lib/api/providers";
import { openApprovalsSheet, usePendingApprovals } from "@/lib/hooks/useApprovals";
import { useProxyAddress } from "@/lib/hooks/useProviderFallback";
import { useUpdateProvider } from "@/lib/hooks/useProviders";
import { pendingReplaceFor } from "@/lib/providers/approvals";
import { PROTOCOL_LABEL_KEY } from "@/lib/providers/presets";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { Section } from "@/components/Section";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { useLockedBy } from "./useLockedBy";

const LINK = "font-label text-accent-text no-underline hover:underline";

interface Props {
  provider: Provider;
  use: ProviderUse;
  /** "401"/"403" (or "") when the endpoint rejects the stored key. */
  rejectedStatus: string | null;
  onReplaceKey: () => void;
}

export function ProviderEndpoint({ provider, use, rejectedStatus, onReplaceKey }: Props) {
  const { t } = useTranslation();
  const approvals = usePendingApprovals();
  const pending = pendingReplaceFor(approvals.data?.approvals, provider.secret_ref);
  const lockedBy = useLockedBy(use);
  const runtime = provider.local_runtime;
  const proxy = useProxyAddress();
  const update = useUpdateProvider();
  const keyed = provider.protocol !== "ollama";

  return (
    <Section title={t("providers.endpoint.title")}>
      <div className="flex flex-col divide-y divide-border-subtle">
        <SettingRow
          label={t("providers.fields.protocol")}
          description={
            lockedBy ? (
              <span className="inline-flex items-center gap-1">
                <Lock className="size-3.5" aria-hidden />
                {t("providers.endpoint.locked", { agents: lockedBy })}
              </span>
            ) : null
          }
        >
          <span className="text-sm">{t(PROTOCOL_LABEL_KEY[provider.protocol])}</span>
        </SettingRow>
        {runtime ? (
          <SettingRow
            label={t("providers.endpoint.runtime")}
            description={
              runtime.wires?.length
                ? t("providers.endpoint.wires", {
                    wires: runtime.wires.map((w) => t(`providers.wires.${w}`, w)).join(", "),
                  })
                : null
            }
          >
            <span className="text-sm">
              {t(`providers.runtimes.${runtime.runtime}`)}
              {runtime.version ? ` ${runtime.version}` : ""}
            </span>
          </SettingRow>
        ) : null}
        <SettingRow label={t("providers.fields.baseUrl")}>
          <TruncatedText text={provider.base_url} mono className="max-w-sm text-xs" />
        </SettingRow>
        {keyed ? (
          <SettingRow
            label={t("providers.endpoint.route")}
            description={t("providers.endpoint.routeValue", { address: proxy })}
          />
        ) : null}
        <SettingRow
          label={t("providers.fields.apiKey")}
          description={
            provider.secret_ref ? (
              <>
                {t("providers.key.stored")}{" "}
                <Link to="/secrets" className={LINK}>
                  {t("providers.key.manage")}
                </Link>
              </>
            ) : (
              t("providers.key.none")
            )
          }
          status={
            pending ? (
              <span role="status" className="flex flex-wrap items-center gap-2">
                <StatusWord tone="warn">{t("providers.key.pending")}</StatusWord>
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto px-0"
                  onClick={openApprovalsSheet}
                >
                  {t("providers.key.review")}
                </Button>
              </span>
            ) : null
          }
        >
          {provider.secret_ref ? (
            <>
              <KeyRound className="size-3.5 text-text-muted" aria-hidden />
              <span className="text-xs text-text-muted">{t("providers.key.secretPrefix")}</span>
              <TruncatedText text={provider.secret_ref} mono className="max-w-[200px] text-xs" />
              {rejectedStatus !== null ? (
                <StatusWord tone="err">
                  {rejectedStatus
                    ? t("providers.key.rejectedWith", { status: rejectedStatus })
                    : t("providers.key.rejected")}
                </StatusWord>
              ) : null}
              <Button variant="outline" size="sm" onClick={onReplaceKey}>
                <KeyRound aria-hidden /> {t("providers.key.replace")}
              </Button>
            </>
          ) : null}
        </SettingRow>
        {keyed ? (
          <SettingRow
            label={t("providers.endpoint.fallback")}
            description={
              runtime
                ? t("providers.endpoint.fallbackLocal")
                : t("providers.endpoint.fallbackSwitch")
            }
          >
            {runtime ? null : (
              <Switch
                checked={provider.fallback}
                disabled={update.isPending}
                onCheckedChange={(fallback) =>
                  update.mutate({ uid: provider.uid, patch: { fallback } })
                }
                aria-label={t("providers.endpoint.fallbackSwitch")}
              />
            )}
          </SettingRow>
        ) : null}
      </div>
    </Section>
  );
}
