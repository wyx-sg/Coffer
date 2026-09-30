// src/components/usage/ViaApiKeyTag.tsx — the "via API key" tag: a subscription agent's requests that went through an API-key provider.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

export function ViaApiKeyTag() {
  const { t } = useTranslation();
  return (
    <Badge variant="secondary" className="h-[18px] px-1.5">
      {t("usage.viaApiKey")}
    </Badge>
  );
}
