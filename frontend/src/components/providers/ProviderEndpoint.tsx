// src/components/providers/ProviderEndpoint.tsx — the Endpoint section: its addresses (or runtime), and the API key's secret.
//
// The key is never shown — only the name of the secret it is stored under
// (a link to that secret's page), write-only, with Replace key — which a rejected
// key moves into the problem box above the rows. A remote provider shows the
// OpenAI- and Anthropic-compatible addresses it has, each saying which agent
// uses it (ADR one-connection-serves-both-wires); a local one its runtime and
// address. Route says agents reach it through Coffer's proxy.
// Problems of the endpoint show here, in a box above the rows: Unreachable
// (Hand off to <Agent>) and Key rejected (Replace key…).
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { SecretRefControl } from "@/components/secret/SecretRefControl";
import { TruncatedText } from "@/components/ui/truncated-text";
import type { Provider } from "@/lib/api/providers";
import { useProxyAddress } from "@/lib/hooks/useProviderPrices";
import { addressesOf } from "@/lib/providers/addresses";
import type { ProbeStatus } from "@/lib/providers/probeStatus";
import { Section } from "@/components/Section";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { ProblemBox } from "./ProblemBox";

interface Props {
  provider: Provider;
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
  status,
  rejectedStatus,
  reason,
  onReplaceKey,
}: Props) {
  const { t } = useTranslation();
  const runtime = provider.local_runtime;
  const proxy = useProxyAddress();
  const keyed = provider.protocol !== "ollama";
  const rejected = status === "keyRejected";
  const host = hostOf(provider.base_url);
  const addresses = addressesOf(provider);

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
        {runtime ? (
          <>
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
                {`${t(`providers.runtimes.${runtime.runtime}`)}${runtime.version ? ` ${runtime.version}` : ""}`}
              </span>
            </SettingRow>
            <SettingRow label={t("providers.fields.baseUrl")}>
              <TruncatedText text={provider.base_url} mono className="max-w-sm text-sm" />
            </SettingRow>
          </>
        ) : (
          (["openai", "anthropic"] as const)
            .filter((key) => addresses[key] !== "")
            .map((key) => (
              <SettingRow
                key={key}
                label={t(`providers.address.${key}.label`)}
                description={t(`providers.address.${key}.help`)}
              >
                <TruncatedText text={addresses[key]} mono className="max-w-sm text-sm" />
              </SettingRow>
            ))
        )}
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
            provider.secret_ref
              ? t("providers.key.stored")
              : runtime
                ? t("providers.key.noneLocal")
                : t("providers.key.none")
          }
        >
          {provider.secret_ref ? (
            <SecretRefControl
              secretRef={provider.secret_ref}
              onReplace={rejected ? undefined : onReplaceKey}
              status={
                rejected ? <StatusWord tone="err">{t("providers.key.rejected")}</StatusWord> : null
              }
            />
          ) : (
            <span className="text-sm">{t("providers.key.noneValue")}</span>
          )}
        </SettingRow>
      </div>
    </Section>
  );
}
