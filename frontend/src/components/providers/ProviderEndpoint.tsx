// src/components/providers/ProviderEndpoint.tsx — the Endpoint section: protocol, runtime, base URL and the API key's secret.
//
// The key is never shown — only the secret reference it is stored under
// (its reference, as the Secrets page shows it), write-only, with Replace key — which a rejected
// key moves into the problem box above the rows. The
// protocol is locked while an agent runs on the provider (spec
// provider-switching "Refuse to move the wire of a live connection"). Route
// says agents reach it through Coffer's proxy.
// Problems of the endpoint show here, in a box above the rows: Unreachable
// (Hand off to <Agent>) and Key rejected (Replace key…).
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound, Lock } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { TruncatedText } from "@/components/ui/truncated-text";
import type { Provider } from "@/lib/api/providers";
import { useProxyAddress } from "@/lib/hooks/useProviderPrices";
import { PROTOCOL_LABEL_KEY } from "@/lib/providers/presets";
import type { ProbeStatus } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { Section } from "@/components/Section";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { ProblemBox } from "./ProblemBox";
import { useLockedBy } from "./useLockedBy";
import { secretReferenceOf } from "@/lib/secretValue";

const LINK = "font-label text-accent-text no-underline hover:underline";

interface Props {
  provider: Provider;
  use: ProviderUse;
  status: ProbeStatus;
  /** "401"/"403" (or "") when the endpoint rejects the stored key. */
  rejectedStatus: string | null;
  /** What the failed probe said, for the Unreachable box and its hand-off. */
  reason: string;
  onReplaceKey: () => void;
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function ProviderEndpoint({
  provider,
  use,
  status,
  rejectedStatus,
  reason,
  onReplaceKey,
}: Props) {
  const { t } = useTranslation();
  const lockedBy = useLockedBy(use);
  const runtime = provider.local_runtime;
  const proxy = useProxyAddress();
  const keyed = provider.protocol !== "ollama";
  const rejected = status === "keyRejected";
  const host = hostOf(provider.base_url);

  return (
    <Section title={t("providers.endpoint.title")} gap="tight">
      <p className="text-xs text-text-muted">{t("providers.endpoint.lead")}</p>
      {status === "unreachable" ? (
        <ProblemBox
          tone="danger"
          title={t("providers.endpoint.unreachableTitle", { host })}
          body={t("providers.endpoint.unreachableBody", { reason })}
        >
          <AgentHandoff
            size="sm"
            prompt={t("providers.endpoint.unreachablePrompt", {
              name: provider.name,
              url: provider.base_url,
              reason,
            })}
          />
        </ProblemBox>
      ) : null}
      {rejected ? (
        <ProblemBox
          tone="danger"
          title={
            rejectedStatus
              ? t("providers.rejected.title", { status: rejectedStatus })
              : t("providers.rejected.titleNoStatus")
          }
          body={t("providers.rejected.body")}
        >
          {provider.secret_ref ? (
            <Button variant="outline" size="sm" onClick={onReplaceKey}>
              <KeyRound aria-hidden /> {t("providers.key.replaceOpen")}
            </Button>
          ) : null}
        </ProblemBox>
      ) : null}
      <div className="flex flex-col divide-y divide-border-subtle">
        <SettingRow
          label={runtime ? t("providers.endpoint.runtime") : t("providers.fields.protocol")}
          description={
            runtime ? (
              runtime.wires?.length ? (
                t("providers.endpoint.wires", {
                  wires: runtime.wires.map((w) => t(`providers.wires.${w}`, w)).join(", "),
                })
              ) : null
            ) : lockedBy ? (
              <span className="inline-flex items-center gap-1">
                <Lock className="size-3.5" aria-hidden />
                {t("providers.endpoint.locked", { agents: lockedBy })}
              </span>
            ) : null
          }
        >
          <span className="text-sm">
            {runtime
              ? `${t(`providers.runtimes.${runtime.runtime}`)}${runtime.version ? ` ${runtime.version}` : ""}`
              : t(PROTOCOL_LABEL_KEY[provider.protocol])}
          </span>
        </SettingRow>
        <SettingRow label={t("providers.fields.baseUrl")}>
          <TruncatedText text={provider.base_url} mono className="max-w-sm text-sm" />
        </SettingRow>
        {keyed && !runtime ? (
          <SettingRow
            label={t("providers.endpoint.route")}
            description={
              <span className="text-sm text-text">
                {t("providers.endpoint.routeThrough")}{" "}
                <span className="font-mono text-xs text-text-muted">{proxy}</span>
              </span>
            }
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
            ) : runtime ? (
              t("providers.key.noneLocal")
            ) : (
              t("providers.key.none")
            )
          }
        >
          {provider.secret_ref ? (
            <>
              <TruncatedText
                text={secretReferenceOf(provider.secret_ref)}
                mono
                className="max-w-[260px] text-xs"
              />
              {rejected ? <StatusWord tone="err">{t("providers.key.rejected")}</StatusWord> : null}
              {rejected ? null : (
                <Button variant="outline" size="sm" onClick={onReplaceKey}>
                  <KeyRound aria-hidden /> {t("providers.key.replaceOpen")}
                </Button>
              )}
            </>
          ) : (
            <span className="text-sm">{t("providers.key.noneValue")}</span>
          )}
        </SettingRow>
      </div>
    </Section>
  );
}
