// frontend/src/components/settings/ProviderConfigCard.tsx
// Read-only "what this connection is" card on the connection detail page.
// Editing goes through the header's Edit dialog (ProviderForm), so nothing here
// is an input. The API key is NEVER rendered — only whether one is stored, which
// is all `credential_ref` tells us. Which agents the connection reaches is not a
// row here either: that is the header's reach control, stated once.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { PROTOCOL_LABEL_KEY } from "@/components/settings/connectionPresets";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Provider } from "@/lib/api/providers";
import { formatDateTime } from "@/lib/utils";

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
          <Row label={t("settings.connections.wireFormat")}>
            {t(PROTOCOL_LABEL_KEY[provider.protocol])}
          </Row>
          <Row label={t("settings.connections.secret")}>
            {provider.credential_ref ? (
              <span>{t("settings.connections.detail.keyStored")}</span>
            ) : (
              <span className="text-muted-foreground">
                {t("settings.connections.detail.keyNone")}
              </span>
            )}
          </Row>
          <Row label={t("resources.cols.description")}>
            {provider.description ? (
              provider.description
            ) : (
              <span className="text-muted-foreground">{t("common.emptyValue")}</span>
            )}
          </Row>
          <Row label={t("settings.connections.detail.created")}>
            {formatDateTime(provider.created_at)}
          </Row>
          <Row label={t("settings.connections.detail.updated")}>
            {formatDateTime(provider.updated_at)}
          </Row>
        </dl>
      </CardContent>
    </Card>
  );
}
