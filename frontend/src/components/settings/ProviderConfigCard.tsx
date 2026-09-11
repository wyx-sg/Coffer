// frontend/src/components/settings/ProviderConfigCard.tsx
// Read-only "what this connection is" card on the connection detail page.
// Editing goes through the header's Edit dialog (ProviderForm), so nothing here
// is an input. The API key is NEVER rendered — only whether one is stored, which
// is all `credential_ref` tells us.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AGENT_LABEL_KEY } from "@/components/settings/connectionPresets";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Provider } from "@/lib/api/providers";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[12rem_1fr] sm:gap-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm break-all">{children}</dd>
    </div>
  );
}

export function ProviderConfigCard({ provider }: { provider: Provider }) {
  const { t } = useTranslation();
  const agents = provider.compatible_agents ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {t("settings.connections.detail.configuration")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3">
          <Row label={t("settings.connections.baseUrl")}>
            <span className="font-mono text-xs">{provider.base_url}</span>
          </Row>
          <Row label={t("settings.connections.wireFormat")}>{provider.protocol}</Row>
          <Row label={t("settings.connections.secret")}>
            {provider.credential_ref ? (
              <span>{t("settings.connections.detail.keyStored")}</span>
            ) : (
              <span className="text-muted-foreground">
                {t("settings.connections.detail.keyNone")}
              </span>
            )}
          </Row>
          <Row label={t("settings.connections.compatibleAgents")}>
            {agents.length === 0 ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <div className="flex flex-wrap gap-1">
                {agents.map((a) => (
                  <span
                    key={a}
                    className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                  >
                    {t(AGENT_LABEL_KEY[a])}
                  </span>
                ))}
              </div>
            )}
          </Row>
          <Row label={t("resources.cols.description")}>
            {provider.description ? (
              provider.description
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </Row>
          <Row label={t("settings.connections.detail.created")}>
            {new Date(provider.created_at).toLocaleString()}
          </Row>
          <Row label={t("settings.connections.detail.updated")}>
            {new Date(provider.updated_at).toLocaleString()}
          </Row>
        </dl>
      </CardContent>
    </Card>
  );
}
