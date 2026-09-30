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
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound, Lock } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { Provider } from "@/lib/api/providers";
import { openApprovalsSheet, usePendingApprovals } from "@/lib/hooks/useApprovals";
import { useProxyAddress } from "@/lib/hooks/useProviderFallback";
import { useUpdateProvider } from "@/lib/hooks/useProviders";
import { pendingReplaceFor } from "@/lib/providers/approvals";
import { PROTOCOL_LABEL_KEY } from "@/lib/providers/presets";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { Section } from "./Section";
import { useLockedBy } from "./useLockedBy";

const LINK = "font-label text-accent-text no-underline hover:underline";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_minmax(0,1fr)] items-baseline gap-4 border-t border-border-subtle py-[7px]">
      <span className="text-xs text-text-muted">{label}</span>
      <div className="min-w-0 break-words text-sm text-text">{children}</div>
    </div>
  );
}

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
  const lockedBy = useLockedBy(provider, use);
  const runtime = provider.local_runtime;
  const proxy = useProxyAddress();
  const update = useUpdateProvider();

  return (
    <Section title={t("providers.endpoint.title")}>
      <div className="flex flex-col">
        <Row label={t("providers.fields.protocol")}>
          <span className="inline-flex min-w-0 items-center gap-1.5">
            {t(PROTOCOL_LABEL_KEY[provider.protocol])}
            {lockedBy ? (
              <>
                <Lock className="size-3.5 text-text-muted" aria-hidden />
                <span className="text-xs text-text-muted">
                  {t("providers.endpoint.locked", { agents: lockedBy })}
                </span>
              </>
            ) : null}
          </span>
        </Row>
        {runtime ? (
          <Row label={t("providers.endpoint.runtime")}>
            {t(`providers.runtimes.${runtime.runtime}`)}
            {runtime.version ? ` ${runtime.version}` : ""}
            {runtime.wires?.length ? (
              <span className="text-xs text-text-muted">
                {" · "}
                {t("providers.endpoint.wires", {
                  wires: runtime.wires.map((w) => t(`providers.wires.${w}`, w)).join(", "),
                })}
              </span>
            ) : null}
          </Row>
        ) : null}
        <Row label={t("providers.fields.baseUrl")}>
          <span className="font-mono text-xs">{provider.base_url}</span>
        </Row>
        {provider.protocol !== "ollama" ? (
          <Row label={t("providers.endpoint.route")}>
            <span className="text-xs text-text-muted">
              {t("providers.endpoint.routeValue", { address: proxy })}
            </span>
          </Row>
        ) : null}
        <Row label={t("providers.fields.apiKey")}>
          {provider.secret_ref ? (
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <KeyRound className="size-3.5 text-text-muted" aria-hidden />
                <span className="text-xs text-text-muted">{t("providers.key.secretPrefix")}</span>
                <span className="truncate font-mono text-xs">{provider.secret_ref}</span>
                {rejectedStatus !== null ? (
                  <StatusWord tone="err">
                    {rejectedStatus
                      ? t("providers.key.rejectedWith", { status: rejectedStatus })
                      : t("providers.key.rejected")}
                  </StatusWord>
                ) : null}
                <span className="ml-auto">
                  <Button variant="outline" size="sm" onClick={onReplaceKey}>
                    <KeyRound aria-hidden /> {t("providers.key.replace")}
                  </Button>
                </span>
              </div>
              {pending ? (
                <div role="status" className="flex flex-wrap items-center gap-2">
                  <StatusWord tone="warn">{t("providers.key.pending")}</StatusWord>
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto px-0"
                    onClick={openApprovalsSheet}
                  >
                    {t("providers.key.review")}
                  </Button>
                </div>
              ) : null}
              <span className="text-xs text-text-muted">
                {t("providers.key.stored")}{" "}
                <Link to="/secrets" className={LINK}>
                  {t("providers.key.manage")}
                </Link>
              </span>
            </div>
          ) : (
            <span className="text-xs text-text-muted">{t("providers.key.none")}</span>
          )}
        </Row>
        {provider.protocol !== "ollama" ? (
          <Row label={t("providers.endpoint.fallback")}>
            {runtime ? (
              <span className="text-xs text-text-muted">
                {t("providers.endpoint.fallbackLocal")}
              </span>
            ) : (
              <label className="inline-flex items-center gap-2 text-sm">
                <Switch
                  checked={provider.fallback}
                  disabled={update.isPending}
                  onCheckedChange={(fallback) =>
                    update.mutate({ uid: provider.uid, patch: { fallback } })
                  }
                  aria-label={t("providers.endpoint.fallbackSwitch")}
                />
                {t("providers.endpoint.fallbackSwitch")}
              </label>
            )}
          </Row>
        ) : null}
      </div>
    </Section>
  );
}
